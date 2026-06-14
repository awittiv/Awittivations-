-- Schedule monthly API key usage reset via pg_cron.
-- Requires pg_cron extension enabled in Supabase: Database → Extensions → pg_cron
-- The reset_monthly_usage() function is defined in 20260604_api_keys.sql.

-- Enable pg_cron if not already enabled
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Remove existing schedule if re-running this migration
SELECT cron.unschedule('reset-api-key-monthly-usage')
WHERE EXISTS (
    SELECT 1 FROM cron.job WHERE jobname = 'reset-api-key-monthly-usage'
);

-- Run at 00:00 UTC on the 1st of each month
SELECT cron.schedule(
    'reset-api-key-monthly-usage',
    '0 0 1 * *',
    $$SELECT reset_monthly_usage()$$
);
