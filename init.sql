CREATE TABLE repositories
(
    id          UUID NOT NULL DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    url         text NOT NULL,
    latest_commit text NULL,
    viewed_commits text[]
);
