alter table public.users
  add column if not exists allowed_data_sources text not null default 'simulator';

alter table public.users
  add column if not exists default_data_source text not null default 'simulator';

update public.users
set allowed_data_sources = 'simulator'
where allowed_data_sources is null
   or trim(allowed_data_sources) = '';

update public.users
set default_data_source = 'simulator'
where default_data_source is null
   or trim(default_data_source) = ''
   or default_data_source not in ('simulator', 'company');
