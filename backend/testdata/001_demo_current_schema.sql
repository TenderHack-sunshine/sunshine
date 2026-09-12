INSERT INTO users (id)
VALUES
    ('user-1'),
    ('user-2'),
    ('user-3'),
    ('user-4'),
    ('user-5'),
    ('user-6')
ON CONFLICT (id) DO NOTHING;


INSERT INTO support_requests (
    id,
    user_id,
    original_message,
    status,
    topic,
    support_level,
    ai_status,
    ai_answer,
    confidence,
    ai_sources,
    created_at,
    updated_at
)
VALUES
(
    'req-1',
    'user-1',
    'Как добавить МЧД?',
    'answered',
    'МЧД',
    'L2',
    'answered',
    'Откройте раздел МЧД и добавьте доверенность.',
    0.91,
    '[]'::jsonb,
    NOW() - INTERVAL '50 minutes',
    NOW() - INTERVAL '49 minutes'
),
(
    'req-2',
    'user-2',
    'Как создать оферту?',
    'answered',
    'Создание оферты',
    'L1',
    'answered',
    'Создайте новую оферту в соответствующем разделе.',
    0.93,
    '[]'::jsonb,
    NOW() - INTERVAL '40 minutes',
    NOW() - INTERVAL '39 minutes'
),
(
    'req-3',
    'user-3',
    'Не получается подписать документ электронной подписью',
    'answered',
    'Электронная подпись',
    'L3',
    'answered',
    'Проверьте сертификат и установленный криптопровайдер.',
    0.88,
    '[]'::jsonb,
    NOW() - INTERVAL '30 minutes',
    NOW() - INTERVAL '28 minutes'
),
(
    'req-4',
    'user-4',
    'Не загружается файл',
    'escalated',
    'Загрузка файлов',
    'L3',
    'escalated',
    '',
    0.32,
    '[]'::jsonb,
    NOW() - INTERVAL '20 minutes',
    NOW() - INTERVAL '18 minutes'
),
(
    'req-5',
    'user-5',
    'Как добавить МЧД в существующую закупку?',
    'answered',
    'Работа с МЧД',
    'L2',
    'answered',
    'Перейдите в карточку закупки и добавьте МЧД.',
    0.89,
    '[]'::jsonb,
    NOW() - INTERVAL '10 minutes',
    NOW() - INTERVAL '9 minutes'
),
(
    'req-6',
    'user-6',
    'Какой статус моей закупки?',
    'need_clarification',
    'Статус закупки',
    'L1',
    'need_clarification',
    'Уточните номер закупки',
    0.72,
    '[]'::jsonb,
    NOW() - INTERVAL '5 minutes',
    NOW() - INTERVAL '4 minutes'
)
ON CONFLICT (id) DO NOTHING;


INSERT INTO messages (
    id,
    support_request_id,
    sender_type,
    text,
    created_at
)
VALUES
(
    'msg-1',
    'req-1',
    'USER',
    'Как добавить МЧД?',
    NOW() - INTERVAL '50 minutes'
),
(
    'msg-2',
    'req-1',
    'AI',
    'Откройте раздел МЧД и добавьте доверенность.',
    NOW() - INTERVAL '49 minutes'
),
(
    'msg-3',
    'req-4',
    'USER',
    'Не загружается файл',
    NOW() - INTERVAL '20 minutes'
),
(
    'msg-4',
    'req-6',
    'USER',
    'Какой статус моей закупки?',
    NOW() - INTERVAL '5 minutes'
),
(
    'msg-5',
    'req-6',
    'AI',
    'Уточните номер закупки',
    NOW() - INTERVAL '4 minutes'
)
ON CONFLICT (id) DO NOTHING;


INSERT INTO tickets (
    id,
    user_id,
    support_request_id,
    status,
    topic,
    support_level,
    original_query,
    conversation_context,
    ai_answer,
    ai_confidence,
    ai_sources,
    operator_id,
    operator_answer,
    created_at,
    updated_at
)
VALUES
(
    'ticket-4',
    'user-4',
    'req-4',
    'WAITING_FOR_OPERATOR',
    'Загрузка файлов',
    'L3',
    'Не загружается файл',
    '',
    '',
    0.32,
    '[]'::jsonb,
    '',
    '',
    NOW() - INTERVAL '18 minutes',
    NOW() - INTERVAL '18 minutes'
)
ON CONFLICT (id) DO NOTHING;


INSERT INTO feedback (
    id,
    user_id,
    support_request_id,
    ticket_id,
    rating,
    comment,
    resolved,
    created_at
)
VALUES
(
    'feedback-1',
    'user-1',
    'req-1',
    NULL,
    2,
    'Ответ правильный, но непонятно, что делать дальше',
    true,
    NOW() - INTERVAL '45 minutes'
)
ON CONFLICT (id) DO NOTHING;