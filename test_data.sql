-- Скрипт для добавления тестовых данных

-- 1. Добавляем тестовые серверы (Outline, VLESS, ShadowSocks)
INSERT INTO servers (name, type_vpn, ip, work, space) VALUES
('🪐 Test Outline Server', 0, '185.58.204.196:37121', true, 50),
('🐊 Test VLESS Server', 1, '185.58.204.196:5555', true, 50),
('🦈 Test ShadowSocks Server', 2, '185.58.204.196:5556', true, 50)
ON CONFLICT (name) DO NOTHING;

-- 2. Обновляем существующих пользователей, назначаем им серверы
UPDATE users
SET server = (SELECT id FROM servers WHERE type_vpn = 0 LIMIT 1)
WHERE tgid = 870499087;  -- @marakoris на Outline

UPDATE users
SET server = (SELECT id FROM servers WHERE type_vpn = 1 LIMIT 1)
WHERE tgid = 5826176899;  -- @Friend_Admin на VLESS

-- 3. Добавляем дополнительных тестовых пользователей на разные серверы
INSERT INTO users (tgid, username, fullname, server, subscription, balance, banned) VALUES
-- Пользователи на Outline
(1111111111, '@test_outline_1', 'Test Outline User 1', (SELECT id FROM servers WHERE type_vpn = 0 LIMIT 1), EXTRACT(EPOCH FROM (NOW() + INTERVAL '30 days'))::bigint, 0, false),
(1111111112, '@test_outline_2', 'Test Outline User 2', (SELECT id FROM servers WHERE type_vpn = 0 LIMIT 1), EXTRACT(EPOCH FROM (NOW() + INTERVAL '30 days'))::bigint, 0, false),
-- Пользователи на VLESS
(2222222221, '@test_vless_1', 'Test VLESS User 1', (SELECT id FROM servers WHERE type_vpn = 1 LIMIT 1), EXTRACT(EPOCH FROM (NOW() + INTERVAL '30 days'))::bigint, 0, false),
(2222222222, '@test_vless_2', 'Test VLESS User 2', (SELECT id FROM servers WHERE type_vpn = 1 LIMIT 1), EXTRACT(EPOCH FROM (NOW() + INTERVAL '30 days'))::bigint, 0, false),
-- Пользователи на ShadowSocks
(3333333331, '@test_ss_1', 'Test ShadowSocks User 1', (SELECT id FROM servers WHERE type_vpn = 2 LIMIT 1), EXTRACT(EPOCH FROM (NOW() + INTERVAL '30 days'))::bigint, 0, false),
(3333333332, '@test_ss_2', 'Test ShadowSocks User 2', (SELECT id FROM servers WHERE type_vpn = 2 LIMIT 1), EXTRACT(EPOCH FROM (NOW() + INTERVAL '30 days'))::bigint, 0, false)
ON CONFLICT (tgid) DO NOTHING;

-- Выводим результаты
SELECT '=== СЕРВЕРЫ ===' as info;
SELECT id, name, type_vpn, ip, work FROM servers;

SELECT '=== ПОЛЬЗОВАТЕЛИ ===' as info;
SELECT id, tgid, username, fullname, server FROM users ORDER BY server;

SELECT '=== СТАТИСТИКА ===' as info;
SELECT
    s.name as server_name,
    s.type_vpn,
    COUNT(u.id) as user_count
FROM servers s
LEFT JOIN users u ON u.server = s.id
GROUP BY s.id, s.name, s.type_vpn
ORDER BY s.type_vpn;
