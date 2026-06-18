-- The Flask backend connects directly as a database role. Browser-side
-- Supabase Data API access is intentionally disabled for these app tables.
alter table public.users enable row level security;
alter table public.chats enable row level security;
alter table public.messages enable row level security;
alter table public.prompts enable row level security;
alter table public.telegram_identities enable row level security;

revoke all privileges on table public.users from anon, authenticated;
revoke all privileges on table public.chats from anon, authenticated;
revoke all privileges on table public.messages from anon, authenticated;
revoke all privileges on table public.prompts from anon, authenticated;
revoke all privileges on table public.telegram_identities from anon, authenticated;

revoke all privileges on sequence public.users_id_seq from anon, authenticated;
revoke all privileges on sequence public.chats_id_seq from anon, authenticated;
revoke all privileges on sequence public.messages_id_seq from anon, authenticated;
revoke all privileges on sequence public.prompts_id_seq from anon, authenticated;
revoke all privileges on sequence public.telegram_identities_id_seq from anon, authenticated;
