DO $$
BEGIN
    -- Rename table if 'paper_positions' exists
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename  = 'paper_positions') THEN
        ALTER TABLE paper_positions RENAME TO positions;
    END IF;

    -- Optional: Rename Indexes for consistency (if they verify existence of table, they likely exist)
    -- But we keep it simple to avoid errors if indexes were named differently manually.
END $$;
