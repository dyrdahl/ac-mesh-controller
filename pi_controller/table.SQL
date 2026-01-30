-- Author: Shane Dyrdahl
-- AC state logging table
CREATE TABLE IF NOT EXISTS ac_data
(
    date     DATE NOT NULL,
    time     TIME NOT NULL,
    ac_state BOOLEAN,

    CONSTRAINT ac_data_pk
        PRIMARY KEY (date, time)
);

-- Settings table (key-value store)
CREATE TABLE IF NOT EXISTS ac_settings
(
    key   VARCHAR(50) PRIMARY KEY,
    value VARCHAR(100) NOT NULL
);

-- Default temperature thresholds
INSERT INTO ac_settings (key, value) VALUES ('max_temp', '78'), ('min_temp', '72')
ON CONFLICT (key) DO NOTHING;
