-- A separate database for the test suite.
--
-- The tests TRUNCATE tables between cases. Pointing them at the development database would mean
-- running `pytest` silently destroyed whatever round the operator had staged -- which is exactly
-- the class of quietly destructive behaviour this system exists to avoid.
--
-- Runs only when the data directory is empty, so `docker compose down -v` is needed to apply a
-- change here.
CREATE DATABASE zaco_test OWNER zaco;
