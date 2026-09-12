CREATE OR REPLACE VIEW analytics_ticket_overview AS

SELECT
    t.id,
    t.ticket_number,
    t.created_at,
    t.topic,
    t.user_id,

    CASE
        WHEN t.is_technical = true THEN 'TECHNICAL'
        WHEN t.is_technical = false THEN 'NON_TECHNICAL'
        ELSE 'UNKNOWN'
    END AS request_type,

    t.initial_support_level,
    t.final_support_level,

    CASE
        WHEN EXISTS (
            SELECT 1
            FROM ticket_events e
            WHERE e.ticket_id = t.id
              AND e.event_type = 'ESCALATED'
              AND e.metadata ->> 'to' = 'OPERATOR'
        )
        THEN t.initial_support_level || ' → OPERATOR'

        WHEN t.initial_support_level IS DISTINCT FROM t.final_support_level
             AND t.final_support_level IS NOT NULL
        THEN t.initial_support_level || ' → ' || t.final_support_level

        ELSE COALESCE(
            t.final_support_level,
            t.initial_support_level
        )
    END AS route,

    CASE
        WHEN t.status = 'open'
            THEN 'IN_PROGRESS'

        WHEN t.operator_involved = true
            THEN 'TRANSFERRED'

        WHEN t.ai_resolved = true
            THEN 'ANSWERED'

        ELSE 'CLOSED'
    END AS result,

    t.status,

    t.ai_resolved,
    t.operator_involved,

    f.rating AS feedback_rating,
    f.reason AS feedback_reason,
    f.comment AS feedback_comment

FROM tickets t

LEFT JOIN feedback f
    ON f.ticket_id = t.id;

CREATE OR REPLACE VIEW analytics_daily_overview AS

SELECT
    CURRENT_DATE AS date,

    COUNT(*) AS total,

    COUNT(*) FILTER (
        WHERE ai_resolved = true
    ) AS ai_resolved,

    COUNT(*) FILTER (
        WHERE operator_involved = true
    ) AS operator_handoff,

    COUNT(*) FILTER (
        WHERE status = 'open'
    ) AS in_progress,

    (
        SELECT COUNT(DISTINCT e.ticket_id)
        FROM ticket_events e

        JOIN tickets tx
            ON tx.id = e.ticket_id

        WHERE e.event_type = 'CLARIFICATION_REQUESTED'
          AND tx.created_at::date = CURRENT_DATE
    ) AS clarification_required

FROM tickets

WHERE created_at::date = CURRENT_DATE;