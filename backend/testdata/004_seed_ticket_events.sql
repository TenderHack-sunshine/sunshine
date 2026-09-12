-- Ticket 2: Создание оферты, решено на L1
INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'CLASSIFIED',
       '{"topic":"Создание оферты","is_technical":false,"support_level":"L1","confidence":0.95}'
FROM tickets WHERE ticket_number = 2;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'ROUTED',
       '{"to":"L1","reason":"NON_TECHNICAL_QUERY"}'
FROM tickets WHERE ticket_number = 2;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'L1_RESOLVED',
       '{"answerability_score":0.93}'
FROM tickets WHERE ticket_number = 2;


-- Ticket 3: Электронная подпись, технический, сразу L3
INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'CLASSIFIED',
       '{"topic":"Электронная подпись","is_technical":true,"support_level":"L3","confidence":0.97}'
FROM tickets WHERE ticket_number = 3;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'ROUTED',
       '{"to":"L3","reason":"TECHNICAL_QUERY"}'
FROM tickets WHERE ticket_number = 3;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'L3_RESOLVED',
       '{"answerability_score":0.88}'
FROM tickets WHERE ticket_number = 3;


-- Ticket 4: Загрузка файлов, технический, L3 не решил, передано оператору
INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'CLASSIFIED',
       '{"topic":"Загрузка файлов","is_technical":true,"support_level":"L3","confidence":0.96}'
FROM tickets WHERE ticket_number = 4;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'ROUTED',
       '{"to":"L3","reason":"TECHNICAL_QUERY"}'
FROM tickets WHERE ticket_number = 4;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'L3_FAILED',
       '{"reason":"UNRESOLVED_TECHNICAL_ISSUE","answerability_score":0.32}'
FROM tickets WHERE ticket_number = 4;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'ESCALATED',
       '{"from":"L3","to":"OPERATOR","reason":"UNRESOLVED_TECHNICAL_ISSUE"}'
FROM tickets WHERE ticket_number = 4;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'OPERATOR_ASSIGNED',
       '{"team":"TECH_SUPPORT"}'
FROM tickets WHERE ticket_number = 4;


-- Ticket 5: Работа с МЧД, L1 -> L2
INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'CLASSIFIED',
       '{"topic":"Работа с МЧД","is_technical":false,"support_level":"L1","confidence":0.91}'
FROM tickets WHERE ticket_number = 5;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'ROUTED',
       '{"to":"L1","reason":"NON_TECHNICAL_QUERY"}'
FROM tickets WHERE ticket_number = 5;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'L1_FAILED',
       '{"reason":"LOW_ANSWERABILITY","answerability_score":0.44}'
FROM tickets WHERE ticket_number = 5;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'ESCALATED',
       '{"from":"L1","to":"L2","reason":"LOW_ANSWERABILITY"}'
FROM tickets WHERE ticket_number = 5;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'L2_RESOLVED',
       '{"answerability_score":0.89}'
FROM tickets WHERE ticket_number = 5;


-- Ticket 6: Статус закупки, потребовалось уточнение
INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'CLASSIFIED',
       '{"topic":"Статус закупки","is_technical":false,"support_level":"L1","confidence":0.72}'
FROM tickets WHERE ticket_number = 6;

INSERT INTO ticket_events (ticket_id, event_type, metadata)
SELECT id, 'CLARIFICATION_REQUESTED',
       '{"reason":"INSUFFICIENT_CONTEXT","question":"Уточните номер закупки"}'
FROM tickets WHERE ticket_number = 6;