-- AI News HQ schema. Idempotent; safe to re-run.
CREATE TABLE IF NOT EXISTS topics (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  slug          VARCHAR(64)  NOT NULL UNIQUE,
  name          VARCHAR(128) NOT NULL,
  description   VARCHAR(512) NOT NULL DEFAULT '',
  display_order INT          NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sources (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  slug            VARCHAR(64)  NOT NULL UNIQUE,
  name            VARCHAR(160) NOT NULL,
  homepage_url    VARCHAR(512) NOT NULL,
  feed_url        VARCHAR(512) NOT NULL,
  -- 'broad'   = covers all of AI; articles get classified per topic
  -- 'topical' = covers one beat; articles inherit the source's topics
  kind            ENUM('broad','topical') NOT NULL,
  quality_tier    TINYINT      NOT NULL DEFAULT 2,
  blurb           VARCHAR(512) NOT NULL DEFAULT '',
  active          TINYINT(1)   NOT NULL DEFAULT 1,
  etag            VARCHAR(255) NULL,
  last_modified   VARCHAR(255) NULL,
  last_fetched_at DATETIME     NULL,
  last_status     VARCHAR(80)  NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS source_topics (
  source_id INT UNSIGNED NOT NULL,
  topic_id  INT UNSIGNED NOT NULL,
  weight    DECIMAL(3,2) NOT NULL DEFAULT 1.00,
  PRIMARY KEY (source_id, topic_id),
  CONSTRAINT fk_st_source FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE,
  CONSTRAINT fk_st_topic  FOREIGN KEY (topic_id)  REFERENCES topics(id)  ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS articles (
  id           BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  source_id    INT UNSIGNED NOT NULL,
  url          VARCHAR(768)  NOT NULL,
  url_hash     CHAR(64)      NOT NULL UNIQUE,
  title        VARCHAR(512)  NOT NULL,
  -- Publisher-syndicated summary. Kept for CLASSIFICATION ONLY; never rendered.
  rss_summary  TEXT          NULL,
  image_url    VARCHAR(1024) NULL,
  published_at DATETIME      NULL,
  fetched_at   DATETIME      NOT NULL,
  KEY idx_published (published_at),
  KEY idx_source    (source_id),
  CONSTRAINT fk_a_source FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS article_topics (
  article_id BIGINT UNSIGNED NOT NULL,
  topic_id   INT UNSIGNED    NOT NULL,
  confidence DECIMAL(3,2)    NOT NULL DEFAULT 1.00,
  method     ENUM('inherited','keyword') NOT NULL,
  PRIMARY KEY (article_id, topic_id),
  KEY idx_topic (topic_id),
  CONSTRAINT fk_at_article FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
  CONSTRAINT fk_at_topic   FOREIGN KEY (topic_id)   REFERENCES topics(id)   ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
