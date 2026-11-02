"""Failure-code catalog fixtures (FR-7.1, FR-7.5): (code, component_group, label) per subtype.

Component groups drive calibration: same code = MATCH, same group = PARTIAL, else MISS.
"""

_SHARED_ELECTRICAL = (
    ("ELEC-BREAKER", "ELECTRICAL", "Breaker tripping"),
    ("ELEC-TRANSFORMER", "ELECTRICAL", "Control transformer failed"),
    ("ELEC-WIRING", "ELECTRICAL", "Loose or damaged wiring"),
)
_SHARED_CONTROLS = (
    ("CTRL-THERMOSTAT", "CONTROLS", "Thermostat / setpoint fault"),
    ("CTRL-BOARD", "CONTROLS", "Control board failed"),
    ("CTRL-SENSOR", "CONTROLS", "Sensor failed or out of calibration"),
)
_SHARED_OTHER = (("OTHER-NO-FAULT", "OTHER", "No fault found"),)

FAILURE_CODES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "RTU": (
        ("COMP-CONTACTOR", "COMPRESSOR", "Compressor contactor failed"),
        ("COMP-CAPACITOR", "COMPRESSOR", "Compressor run capacitor failed"),
        ("COMP-WINDING", "COMPRESSOR", "Compressor winding failure"),
        ("COMP-SEIZED", "COMPRESSOR", "Compressor seized"),
        ("FAN-COND-MOTOR", "CONDENSER_FAN", "Condenser fan motor failed"),
        ("FAN-COND-BLADE", "CONDENSER_FAN", "Condenser fan blade damaged"),
        ("FAN-EVAP-BELT", "SUPPLY_FAN", "Supply fan belt worn or broken"),
        ("FAN-EVAP-MOTOR", "SUPPLY_FAN", "Supply fan motor failed"),
        ("REF-LEAK", "REFRIGERANT", "Refrigerant leak"),
        ("REF-TXV", "REFRIGERANT", "Expansion valve failed"),
        ("REF-OVERCHARGE", "REFRIGERANT", "Refrigerant overcharge"),
        ("AIR-FILTER", "AIRSIDE", "Filter clogged"),
        ("AIR-ECONOMIZER", "AIRSIDE", "Economizer damper stuck"),
        *_SHARED_ELECTRICAL,
        *_SHARED_CONTROLS,
        *_SHARED_OTHER,
    ),
    "AHU": (
        ("FAN-SUPPLY-MOTOR", "SUPPLY_FAN", "Supply fan motor failed"),
        ("FAN-SUPPLY-BEARING", "SUPPLY_FAN", "Supply fan bearing worn"),
        ("FAN-SUPPLY-BELT", "SUPPLY_FAN", "Supply fan belt worn or broken"),
        ("COIL-LEAK", "COILS", "Coil leak"),
        ("COIL-FOULED", "COILS", "Coil fouled"),
        ("AIR-FILTER", "AIRSIDE", "Filter clogged"),
        ("AIR-DAMPER", "AIRSIDE", "Damper actuator failed"),
        ("VFD-FAULT", "ELECTRICAL", "Variable frequency drive fault"),
        *_SHARED_ELECTRICAL,
        *_SHARED_CONTROLS,
        *_SHARED_OTHER,
    ),
}
