-- email-pool-worker D1 schema
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  address TEXT NOT NULL,
  sender TEXT,
  subject TEXT,
  text TEXT,
  html TEXT,
  received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_address ON messages(address);
CREATE INDEX IF NOT EXISTS idx_messages_received_at ON messages(received_at);

CREATE TABLE IF NOT EXISTS addresses (
  address TEXT PRIMARY KEY,
  created_at TEXT NOT NULL
);
