import sqlite3

DB_PATH = "hospital.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    #configration command which enables foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_tables():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS doctors (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT NOT NULL,
            specialty TEXT NOT NULL,
            available INTEGER DEFAULT 1,
            emergency INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS doctor_availability (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id              INTEGER NOT NULL,
            day_of_week            INTEGER,
            avail_date             TEXT,
            start_time             TEXT NOT NULL,
            end_time               TEXT NOT NULL,
            max_patients           INTEGER NOT NULL DEFAULT 4,
            slot_duration_minutes  INTEGER,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        );

        CREATE TABLE IF NOT EXISTS doctor_slots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER NOT NULL,
            slot_date TEXT NOT NULL,
            slot_time TEXT NOT NULL,
            is_booked INTEGER DEFAULT 0,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        );

        CREATE TABLE IF NOT EXISTS patients (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone     TEXT,
            dob       TEXT
        );

        CREATE TABLE IF NOT EXISTS appointments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id   INTEGER NOT NULL,
            doctor_id    INTEGER NOT NULL,
            slot_id      INTEGER,
            scheduled_at TEXT NOT NULL,
            status       TEXT DEFAULT 'confirmed',
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id)  REFERENCES doctors(id),
            FOREIGN KEY (slot_id)    REFERENCES doctor_slots(id)
        );

        CREATE TABLE IF NOT EXISTS insurance_providers (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL,
            accepted INTEGER DEFAULT 1
        );
    """)
    ensure_emergency_column(conn)
    ensure_doctor_availability_table(conn)
    conn.commit()
    conn.close()
    print("Tables created successfully.")


def ensure_doctor_availability_table(conn=None) -> None:
    own = conn is None
    if own:
        conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS doctor_availability (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id              INTEGER NOT NULL,
            day_of_week            INTEGER,
            avail_date             TEXT,
            start_time             TEXT NOT NULL,
            end_time               TEXT NOT NULL,
            max_patients           INTEGER NOT NULL DEFAULT 4,
            slot_duration_minutes  INTEGER,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
        """
    )
    if own:
        conn.commit()
        conn.close()


def ensure_emergency_column(conn=None) -> None:
    
    own = conn is None
    if own:
        conn = get_connection()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(doctors)")}
    if "emergency" not in cols:
        conn.execute("ALTER TABLE doctors ADD COLUMN emergency INTEGER DEFAULT 0")
    conn.execute(
        "UPDATE doctors SET emergency = 1 WHERE LOWER(name) LIKE '%shah%'"
    )
    if own:
        conn.commit()
        conn.close()
