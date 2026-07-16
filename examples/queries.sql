-- Top repositories
SELECT repository, commits, authors, insertions, deletions, last_activity
FROM v_repository_summary
ORDER BY commits DESC;

-- Activity by year and month
SELECT activity_year AS year, activity_month AS month, COUNT(*) AS commits
FROM v_commits
GROUP BY activity_year, activity_month
ORDER BY year, month;

-- Top canonical authors
SELECT author_name, author_email, commits, repositories, active_days
FROM v_author_summary
ORDER BY commits DESC
LIMIT 50;

-- Weekday/hour matrix (Monday = 0)
SELECT activity_weekday, activity_hour, COUNT(*) AS commits
FROM v_commits
GROUP BY activity_weekday, activity_hour
ORDER BY activity_weekday, activity_hour;

-- Historical file hotspots
SELECT repository, path, COUNT(*) AS touches,
       SUM(COALESCE(insertions, 0) + COALESCE(deletions, 0)) AS churn
FROM v_file_changes
GROUP BY repository, path
ORDER BY touches DESC, churn DESC
LIMIT 100;
