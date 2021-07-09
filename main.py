import datetime
import string
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Iterator, List, Optional, Set
from uuid import UUID

import fastapi
import github as gh
import psycopg2
import psycopg2.extensions
from dotenv import load_dotenv
from fastapi import Depends
from github.Commit import Commit as GHCommit
from pydantic import BaseConfig, BaseModel, BaseSettings, HttpUrl, SecretStr
from pydantic.fields import ModelField
from starlette.responses import Response

if TYPE_CHECKING:
    from pydantic.typing import CallableGenerator

load_dotenv()


class Settings(BaseSettings):
    github_token: SecretStr
    postgres_dsn: SecretStr


app = fastapi.FastAPI()
settings = Settings()


class SHAStr(str):
    InvalidSHAStr = type('InvalidSHAStr', (ValueError,), {})

    @classmethod
    def from_str(cls, value: Any):
        if not (
                isinstance(value, str)
                and len(value) == 40
                and all(map(lambda x: x in string.hexdigits, value))
        ):
            raise cls.InvalidSHAStr(value)

        return cls(value)

    @classmethod
    def __get_validators__(cls) -> 'CallableGenerator':
        yield cls.validate

    @classmethod
    def validate(cls, value: Any, field: 'ModelField', config: 'BaseConfig') -> 'SHAStr':
        if value.__class__ == cls:
            return value

        return cls.from_str(value)


class LikedRepository(BaseModel):
    id: UUID
    name: str
    url: HttpUrl
    latest_commit: Optional[SHAStr]
    viewed_commits: Set[SHAStr]


class Commit(BaseModel):
    name: str
    sha: SHAStr
    link: HttpUrl
    additions: int
    deletions: int
    last_modified: Optional[datetime.datetime]
    viewed: bool


class BusinessLogic:
    ShouldBeUpdated = type('ShouldBeUpdated', (Exception,), {})

    def see_repo(self, repo: LikedRepository, should_be_updated: list[LikedRepository]) -> Iterator[Commit]:
        g = gh.Github(login_or_token=settings.github_token.get_secret_value())
        r = g.get_repo(repo.url.removeprefix('https://github.com/'))
        viewed_commits: Deque[GHCommit] = deque()

        for commit in r.get_commits():
            cur_sha = SHAStr.from_str(commit.sha)

            if cur_sha == repo.latest_commit:
                break
            elif cur_sha in repo.viewed_commits:
                viewed_commits.append(commit)
            else:
                while len(viewed_commits):
                    yield self._prepare_commit(viewed_commits.pop(), viewed=True)
                viewed_commits.clear()
                yield self._prepare_commit(commit, viewed=False)

        if len(viewed_commits):
            repo.latest_commit = SHAStr.from_str(viewed_commits[0].sha)
            repo.viewed_commits -= set(map(lambda x: SHAStr.from_str(x.sha), viewed_commits))
            should_be_updated.append(repo.copy())

    @staticmethod
    def _prepare_commit(commit: GHCommit, viewed: bool) -> Commit:
        return Commit(
            name=commit.commit.message,
            sha=SHAStr.from_str(commit.sha),
            link=commit.html_url,
            additions=commit.stats.additions,
            deletions=commit.stats.deletions,
            last_modified=(
                datetime.datetime.strptime(commit.last_modified, "%a, %d %b %Y %H:%M:%S %Z")
                if commit.last_modified else None
            ),
            viewed=viewed,
        )


class PostgresGateway:
    def __init__(self, cursor: psycopg2.extensions.cursor):
        self._cursor = cursor

    @classmethod
    def get_instance(cls):
        with psycopg2.connect(settings.postgres_dsn.get_secret_value()) as conn:  # type: psycopg2.extensions.connection
            cur = conn.cursor()  # type: psycopg2.extensions.cursor
            yield cls(cur)

    def get_repositories(self) -> List[LikedRepository]:
        self._cursor.execute("""
            SELECT id, name, url, latest_commit, viewed_commits
            FROM repositories
        """)
        return [LikedRepository(**dict(zip(
            ('id', 'name', 'url', 'latest_commit', 'viewed_commits'), row
        ))) for row in self._cursor.fetchall()]

    def get_repository(self, repo_id: UUID) -> Optional[LikedRepository]:
        self._cursor.execute("""
            SELECT id, name, url, latest_commit, viewed_commits
            FROM repositories
            WHERE id = %s
        """, [str(repo_id)])
        row = self._cursor.fetchone()
        if row is None:
            return None
        return LikedRepository(**dict(zip(
            ('id', 'name', 'url', 'latest_commit', 'viewed_commits'), row
        )))

    def update_repository(self, repo: LikedRepository):
        self._cursor.execute("""
            UPDATE repositories
            SET latest_commit = %s,
                viewed_commits = %s
            WHERE id = %s
        """, [repo.latest_commit, [*repo.viewed_commits], str(repo.id)])


class NewsItem(BaseModel):
    id: UUID
    name: str
    url: HttpUrl
    commits: list[Commit]


@app.get('/api/news')
def news(pg: PostgresGateway = Depends(PostgresGateway.get_instance)):
    repos = pg.get_repositories()
    should_be_updated: list[LikedRepository] = []

    resp = [NewsItem(
        id=repo.id,
        name=repo.name,
        url=repo.url,
        commits=[*BusinessLogic().see_repo(repo, should_be_updated)],
    ) for repo in repos]

    for repo in should_be_updated:
        pg.update_repository(repo)
    return resp


@app.post('/api/viewed')
def set_viewed(repo_id: UUID, commit_sha: SHAStr, pg: PostgresGateway = Depends(PostgresGateway.get_instance)):
    if repo := pg.get_repository(repo_id):
        repo.viewed_commits.add(commit_sha)
        pg.update_repository(repo)
        return repo


@app.delete('/api/viewed')
def unset_viewed(repo_id: UUID, commit_sha: SHAStr, pg: PostgresGateway = Depends(PostgresGateway.get_instance)):
    if repo := pg.get_repository(repo_id):
        repo.viewed_commits.discard(commit_sha)
        pg.update_repository(repo)
        return repo


def get_static_handler(fs_path, media_type):
    def handler():
        with open(fs_path) as fp:
            return Response(fp.read(), media_type=media_type)

    return handler


def init_static():
    for web_path, fs_path, media_type in [
        ('/', 'index.html', 'text/html'),
        ('/_front/script.js', 'script.js', 'text/javascript'),
    ]:
        app.get(web_path, response_class=Response)(get_static_handler(fs_path, media_type))


init_static()
