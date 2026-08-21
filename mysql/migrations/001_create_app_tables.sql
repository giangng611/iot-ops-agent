create table if not exists users (
  id int not null auto_increment,
  username varchar(255) not null,
  password_hash text not null,
  created_at varchar(64) not null,
  allowed_data_sources varchar(255) not null default 'simulator',
  default_data_source varchar(64) not null default 'simulator',
  primary key (id),
  unique key users_username_key (username)
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists chats (
  id int not null auto_increment,
  user_id int null,
  title varchar(255) not null,
  created_at varchar(64) not null,
  is_pinned tinyint(1) not null default 0,
  primary key (id),
  key chats_user_pinned_id_idx (user_id, is_pinned, id),
  constraint chats_user_id_fk
    foreign key (user_id) references users (id)
    on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists messages (
  id int not null auto_increment,
  chat_id int not null,
  role varchar(64) not null,
  content longtext not null,
  reasoning_steps longtext null,
  token_usage text null,
  created_at varchar(64) not null,
  primary key (id),
  key messages_chat_id_idx (chat_id, id),
  constraint messages_chat_id_fk
    foreign key (chat_id) references chats (id)
    on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists prompts (
  id int not null auto_increment,
  user_id int not null,
  title varchar(255) not null,
  command text not null,
  category varchar(255) not null,
  is_default tinyint(1) not null default 0,
  created_at varchar(64) not null default (date_format(current_timestamp, '%Y-%m-%dT%H:%i:%s')),
  primary key (id),
  key prompts_user_default_id_idx (user_id, is_default, id),
  constraint prompts_user_id_fk
    foreign key (user_id) references users (id)
    on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists telegram_identities (
  id int not null auto_increment,
  telegram_user_id varchar(255) not null,
  user_id int not null,
  telegram_username varchar(255) null,
  role varchar(64) not null default 'viewer',
  allowed_data_sources varchar(255) not null default 'simulator',
  is_active tinyint(1) not null default 1,
  created_at varchar(64) not null,
  updated_at varchar(64) not null,
  primary key (id),
  unique key telegram_identities_telegram_user_id_key (telegram_user_id),
  key telegram_identities_user_id_idx (user_id),
  constraint telegram_identities_user_id_fk
    foreign key (user_id) references users (id)
    on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;

create table if not exists telegram_link_codes (
  id int not null auto_increment,
  code_hash varchar(255) not null,
  user_id int not null,
  expires_at varchar(64) not null,
  used_at varchar(64) null,
  created_at varchar(64) not null,
  primary key (id),
  unique key telegram_link_codes_code_hash_key (code_hash),
  key telegram_link_codes_user_id_idx (user_id),
  constraint telegram_link_codes_user_id_fk
    foreign key (user_id) references users (id)
    on delete cascade
) engine=InnoDB default charset=utf8mb4 collate=utf8mb4_unicode_ci;
