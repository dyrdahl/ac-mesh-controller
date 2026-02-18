-- Author: Shane Dyrdahl
-- AC Control System Database Schema

-- =============================================================================
-- AC State Logging
-- =============================================================================
CREATE TABLE IF NOT EXISTS ac_data
(
    date        DATE NOT NULL,
    time        TIME NOT NULL,
    ac_state    BOOLEAN,
    temperature DOUBLE PRECISION,

    CONSTRAINT ac_data_pk
        PRIMARY KEY (date, time)
);

-- =============================================================================
-- Settings (key-value store)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ac_settings
(
    key   VARCHAR(50) PRIMARY KEY,
    value VARCHAR(100) NOT NULL
);

-- Default settings
INSERT INTO ac_settings (key, value) VALUES
    ('max_temp', '78'),
    ('min_temp', '72'),
    ('ac_allowed', 'true')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- Mesh Network Node Status
-- =============================================================================
CREATE TABLE IF NOT EXISTS mesh_nodes
(
    node_id      INTEGER PRIMARY KEY,
    name         VARCHAR(50) NOT NULL,
    last_seen    TIMESTAMP,
    status       VARCHAR(10) DEFAULT 'offline',
    last_message VARCHAR(100)
);

-- Default nodes
INSERT INTO mesh_nodes (node_id, name) VALUES
    (1, 'AC Relay'),
    (2, 'Keypad/LCD')
ON CONFLICT (node_id) DO NOTHING;

-- =============================================================================
-- Weather Data (from Open-Meteo API)
-- =============================================================================
CREATE TABLE IF NOT EXISTS weather_data
(
    id           SERIAL PRIMARY KEY,
    timestamp    TIMESTAMPTZ DEFAULT NOW(),
    outdoor_temp DOUBLE PRECISION NOT NULL,
    humidity     DOUBLE PRECISION,
    conditions   VARCHAR(50)
);

-- Index for efficient time-based queries
CREATE INDEX IF NOT EXISTS idx_weather_timestamp ON weather_data(timestamp);
