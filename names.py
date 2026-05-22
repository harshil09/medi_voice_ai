"""Run once: python names.py"""
from database import get_connection, create_tables

create_tables()

conn = get_connection()
cursor = conn.cursor()

if cursor.execute("SELECT COUNT(*) FROM doctors").fetchone()[0] > 0:
    conn.close()
    print("Already seeded. Delete hospital.db to re-seed.")
    raise SystemExit(0)

cursor.executemany(
    "INSERT INTO doctors (name, specialty, available, emergency) VALUES (?, ?, ?, ?)",
    [
        ("Dr. Shah", "cardiologist", 1, 1),
        ("Dr. Mehta", "cardiologist", 1, 0),
        ("Dr. Patel", "general", 1, 0),
        ("Dr. Smith", "general", 1, 0),
        ("Dr. Kapoor", "orthopedic", 1, 0),
    ],
)

doctor_rows = {row[1]: row[0] for row in cursor.execute("SELECT id, name FROM doctors")}

# Dynamic slots: window minutes / max_patients = slot length.
# Mehta: 09:00-11:00 (120 min), 4 patients → 30 min → 09:00, 09:30, 10:00, 10:30
# Patel: 12:00-13:00 (60 min), 4 patients → 15 min → 12:00, 12:15, 12:30, 12:45
# Smith: 14:00-16:00 (120 min), 4 patients → 30 min
# Kapoor: 10:00-12:00 (120 min), 4 patients → 30 min
dates = ("2026-05-26", "2026-05-27", "2026-05-28")
availability = []
for d in dates:
    availability.extend(
        [
            (doctor_rows["Dr. Mehta"], None, d, "09:00", "11:00", 4, None),
            (doctor_rows["Dr. Patel"], None, d, "12:00", "13:00", 4, None),
            (doctor_rows["Dr. Smith"], None, d, "14:00", "16:00", 4, None),
            (doctor_rows["Dr. Kapoor"], None, d, "10:00", "12:00", 4, None),
        ]
    )

cursor.executemany(
    """
    INSERT INTO doctor_availability
        (doctor_id, day_of_week, avail_date, start_time, end_time, max_patients, slot_duration_minutes)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    availability,
)

cursor.executemany(
    "INSERT INTO insurance_providers (name, accepted) VALUES (?, ?)",
    [
        ("Blue Cross Blue Shield", 1),
        ("Aetna", 1),
        ("UnitedHealthcare", 1),
        ("Medicare", 1),
        ("Medicaid", 1),
        ("Cigna", 0),
    ],
)

conn.commit()
conn.close()
print("Seeded successfully (dynamic availability; no hardcoded doctor_slots).")
