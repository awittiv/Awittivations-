-- Admin users table
CREATE TABLE IF NOT EXISTS admins (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE admins ENABLE ROW LEVEL SECURITY;

-- Users can check their own admin status
CREATE POLICY "admins_self_read" ON admins
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

-- To grant admin access, run as service role:
-- INSERT INTO admins (user_id) VALUES ('<user-uuid>');
