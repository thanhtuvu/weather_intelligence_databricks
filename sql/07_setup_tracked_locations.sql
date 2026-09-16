CREATE TABLE IF NOT EXISTS weather_intelligence.bronze.tracked_locations (
    location STRING NOT NULL
    ,added_at TIMESTAMP NOT NULL
    ,active BOOLEAN NOT NULL
) USING DELTA;

-- Seed with Honolulu, since it's already ingested, backfilled, and tested end-to-end
INSERT INTO weather_intelligence.bronze.tracked_locations
VALUES ('Honolulu, HI', current_timestamp(), true);

-- To track a new city later, just:
-- INSERT INTO weather_intelligence.bronze.tracked_locations VALUES ('Seattle, WA', current_timestamp(), true);

-- To pause a city without losing its history:
-- UPDATE weather_intelligence.bronze.tracked_locations SET active = false WHERE location = 'Seattle, WA';