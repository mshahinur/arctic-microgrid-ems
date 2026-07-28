"""
Arctic Microgrid EMS Decision Simulation
-----------------------------------------
Simulates 48 hours of a hybrid battery-hydrogen-diesel microgrid serving
a remote Arctic community, applying the rule-based decision logic:

    Priority order: Renewables -> Battery -> Hydrogen -> Diesel

Battery capacity is derated at low temperatures (cold-climate effect),
consistent with the literature on BESS behavior below -20C.

Author: Shahinur Rahman Chowdhury (prep for Volt-Age / Prof. Zaghib interview)
"""

import numpy as np
import matplotlib.pyplot as plt

# ---------------------------------------------------------------
# 1. SIMULATION SETUP
# ---------------------------------------------------------------
HOURS = 48
dt = 1.0  # 1-hour timestep

rng = np.random.default_rng(42)

# Synthetic solar generation (kW) - Arctic winter: short daylight, low output
hour_of_day = np.arange(HOURS) % 24
solar_gen = np.clip(
    8 * np.sin((hour_of_day - 10) / 5.0) + rng.normal(0, 0.5, HOURS), 0, None
)
solar_gen[(hour_of_day < 9) | (hour_of_day > 15)] = 0  # short winter daylight

# Wind generation (kW) - more consistent, some variability
wind_gen = np.clip(5 + 3 * np.sin(hour_of_day / 6.0) + rng.normal(0, 1.0, HOURS), 0, None)

renewable_gen = solar_gen + wind_gen  # total renewable supply (kW)

# Community load demand (kW) - peaks morning/evening, heating-driven in Arctic
load_demand = (
    12
    + 6 * np.sin((hour_of_day - 7) / 4.0) ** 2
    + rng.normal(0, 1.0, HOURS)
)
load_demand = np.clip(load_demand, 6, None)

# Ambient temperature (deg C) - Arctic winter profile
ambient_temp = -25 + 5 * np.sin(hour_of_day / 12.0) + rng.normal(0, 1.0, HOURS)

# ---------------------------------------------------------------
# 2. BATTERY MODEL PARAMETERS
# ---------------------------------------------------------------
CBAT_NOMINAL = 100.0       # kWh, nominal capacity at reference temp
SOC = 60.0                 # initial SoC (%)
SOC_HIGH = 80.0
SOC_LOW = 30.0
SOC_CRITICAL = 20.0
SOC_MIN, SOC_MAX = 10.0, 95.0

H2_TANK = 100.0             # kg, hydrogen reserve
H2_LOW_THRESHOLD = 15.0     # kg
FUEL_CELL_EFFICIENCY = 0.5  # kWh per kg H2 (approx, simplified)
ELECTROLYZER_EFFICIENCY = 0.6  # kg H2 produced per kWh surplus (simplified)

def capacity_derating(temp_c):
    """Cold-climate battery capacity derating factor (simplified linear model).
    Below -20C, usable capacity drops significantly (consistent with
    literature on Li-ion performance in extreme cold)."""
    if temp_c >= 0:
        return 1.0
    elif temp_c >= -20:
        return 1.0 - 0.01 * abs(temp_c)       # mild derating
    else:
        return max(0.6, 1.0 - 0.02 * abs(temp_c))  # steeper derating below -20C

# ---------------------------------------------------------------
# 3. EMS DECISION LOGIC (rule-based, per flowchart)
# ---------------------------------------------------------------
soc_history = []
h2_history = []
decision_history = []
diesel_kwh = []
unmet_load = []

for t in range(HOURS):
    gen = renewable_gen[t]
    load = load_demand[t]
    temp = ambient_temp[t]

    derate = capacity_derating(temp)
    usable_cbat = CBAT_NOMINAL * derate
    net = gen - load  # positive = surplus, negative = deficit

    decision = None
    diesel_used = 0.0
    deficit_unmet = 0.0

    if net >= 0:
        # Surplus renewable power available
        if SOC < SOC_MAX:
            charge_kwh = min(net * dt, (SOC_MAX - SOC) / 100 * usable_cbat)
            SOC += (charge_kwh / usable_cbat) * 100
            net -= charge_kwh
            decision = "CHARGE (battery)"
        if net > 0:
            # still surplus after charging -> electrolysis
            h2_produced = net * ELECTROLYZER_EFFICIENCY * dt
            H2_TANK += h2_produced
            decision = "CHARGE + H2 PRODUCTION"
    else:
        deficit = -net
        if SOC > SOC_LOW:
            discharge_kwh = min(deficit * dt, (SOC - SOC_MIN) / 100 * usable_cbat)
            SOC -= (discharge_kwh / usable_cbat) * 100
            deficit -= discharge_kwh
            decision = "DISCHARGE (battery)"
        if deficit > 0.01 and H2_TANK > H2_LOW_THRESHOLD:
            h2_needed = deficit / FUEL_CELL_EFFICIENCY * dt
            h2_used = min(h2_needed, H2_TANK - H2_LOW_THRESHOLD)
            H2_TANK -= h2_used
            deficit -= h2_used * FUEL_CELL_EFFICIENCY
            decision = (decision + " + HYDROGEN") if decision else "HYDROGEN"
        if deficit > 0.01:
            diesel_used = deficit
            decision = (decision + " + DIESEL") if decision else "DIESEL (last resort)"

    SOC = np.clip(SOC, SOC_MIN, SOC_MAX)
    soc_history.append(SOC)
    h2_history.append(H2_TANK)
    decision_history.append(decision)
    diesel_kwh.append(diesel_used)
    unmet_load.append(deficit_unmet)

# ---------------------------------------------------------------
# 4. RESULTS SUMMARY
# ---------------------------------------------------------------
total_diesel = sum(diesel_kwh)
diesel_hours = sum(1 for d in diesel_kwh if d > 0)
h2_final = h2_history[-1]
soc_min_reached = min(soc_history)

print("=" * 60)
print("EMS SIMULATION RESULTS (48-hour Arctic microgrid run)")
print("=" * 60)
print(f"Total diesel energy used      : {total_diesel:.1f} kWh")
print(f"Hours diesel generator engaged: {diesel_hours} / {HOURS}")
print(f"Final hydrogen reserve        : {h2_final:.1f} kg (started at 100 kg)")
print(f"Minimum SoC reached           : {soc_min_reached:.1f} %")
print(f"Final battery SoC             : {soc_history[-1]:.1f} %")
print("=" * 60)
print("\nSample decision log (first 12 hours):")
for t in range(12):
    print(f"  Hour {t:2d} | Temp {ambient_temp[t]:6.1f}C | "
          f"Renew {renewable_gen[t]:5.1f}kW | Load {load_demand[t]:5.1f}kW | "
          f"SoC {soc_history[t]:5.1f}% | -> {decision_history[t]}")

# ---------------------------------------------------------------
# 5. PLOT
# ---------------------------------------------------------------
fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

axes[0].plot(renewable_gen, label="Renewable gen (kW)", color="#2a9d8f")
axes[0].plot(load_demand, label="Load demand (kW)", color="#e76f51")
axes[0].fill_between(range(HOURS), 0, diesel_kwh, color="#264653", alpha=0.6, label="Diesel used (kWh)")
axes[0].set_ylabel("kW")
axes[0].legend(loc="upper right", fontsize=8)
axes[0].set_title("Arctic Microgrid EMS Simulation — 48 Hours")

axes[1].plot(soc_history, color="#264653", label="Battery SoC (%)")
axes[1].axhline(SOC_HIGH, color="gray", linestyle="--", linewidth=0.8)
axes[1].axhline(SOC_LOW, color="gray", linestyle="--", linewidth=0.8)
axes[1].axhline(SOC_CRITICAL, color="red", linestyle="--", linewidth=0.8)
axes[1].set_ylabel("SoC (%)")
axes[1].legend(loc="upper right", fontsize=8)

axes[2].plot(h2_history, color="#e9c46a", label="H2 reserve (kg)")
axes[2].plot(ambient_temp, color="#3d5a80", label="Ambient temp (C)", alpha=0.6)
axes[2].set_ylabel("kg / C")
axes[2].set_xlabel("Hour")
axes[2].legend(loc="upper right", fontsize=8)

plt.tight_layout()
plt.savefig("/home/claude/ems_sim/ems_simulation_result.png", dpi=150)
print("\nPlot saved to ems_simulation_result.png")
