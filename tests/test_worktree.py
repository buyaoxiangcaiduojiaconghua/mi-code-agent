"""ch14 Worktree 单测"""

import pytest

from micodeagent.tool.ctx import cwd_from_ctx, resolve_path, with_cwd
from micodeagent.worktree.slug import flat_slug, validate_slug


class TestSlug:
    @pytest.mark.parametrize("slug", ["alice", "team/alice", "v1.0", "a_b", "a-b", "a.b"])
    def test_valid(self, slug):
        validate_slug(slug)

    @pytest.mark.parametrize(
        "slug",
        ["", "x" * 65, "..", "./x", "a//b", "/x", "a/", "a b", "a;b"],
    )
    def test_invalid(self, slug):
        with pytest.raises(ValueError):
            validate_slug(slug)

    def test_flat(self):
        assert flat_slug("team/alice") == "team+alice"
        assert flat_slug("alice") == "alice"


class TestToolCtx:
    def test_resolve_relative(self, tmp_path):
        with with_cwd(str(tmp_path)):
            assert resolve_path("a.txt") == str(tmp_path / "a.txt")

    def test_resolve_absolute(self, tmp_path):
        with with_cwd(str(tmp_path)):
            assert resolve_path("/etc/passwd") == "/etc/passwd"

    def test_resolve_empty(self, tmp_path):
        with with_cwd(str(tmp_path)):
            assert resolve_path("") == str(tmp_path)

    def test_no_ctx_falls_back_to_cwd(self):

        assert resolve_path("x.txt") == str(__import__("pathlib").Path.cwd() / "x.txt")

    def test_cwd_from_ctx(self, tmp_path):
        assert cwd_from_ctx() is None
        with with_cwd(str(tmp_path)):
            assert cwd_from_ctx() == str(tmp_path)


class TestManagerConstruct:
    def test_not_git_root(self, tmp_path):
        from micodeagent.worktree.manager import Manager

        with pytest.raises(ValueError, match="not a git repo root"):
            Manager(str(tmp_path))
