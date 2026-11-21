# x-post-read

A small Agent Skill for reading one known public X/Twitter post via
[FxEmbed](https://docs.fxembed.com/api/introduction/).
Python 3.9+ standard library only; no API key, cookies, dependencies, or MCP server.
Independently written implementation. MIT licensed.

## Install and use

With [Vercel's skills CLI](https://github.com/vercel-labs/skills)
(Node.js 22.20+), run from your target project:

```sh
npx skills add yuu-biz/x-post-read
```

Choose your agent, or select Claude Code and Codex explicitly without prompts:

```sh
npx skills add yuu-biz/x-post-read --skill x-post-read -a claude-code -a codex -y
```

Installation is project-local by default; optionally add `-g` / `--global`
for a personal installation across projects. Use `--list` to preview discovery.
The root `SKILL.md` and bundled Python script install directly from GitHub;
this repository does not need an npm package. Python is still required to read posts.

Alternatively, install with Git:

Clone into **one** of these directories; run from the project where you want the skill.
Do not overwrite an existing installation.

Claude Code (project skill):

```sh
git clone https://github.com/yuu-biz/x-post-read.git .claude/skills/x-post-read
```

Then ask Claude Code: `/x-post-read https://x.com/jack/status/20`.
For personal installation, clone into `~/.claude/skills/x-post-read` instead.
See [Claude Code skills](https://code.claude.com/docs/en/skills).

Codex (project skill):

```sh
git clone https://github.com/yuu-biz/x-post-read.git .agents/skills/x-post-read
```

Then ask Codex: `$x-post-read Read https://x.com/jack/status/20`.
For personal installation, clone into `~/.agents/skills/x-post-read` instead.
Restart the agent if discovery has not refreshed.
See [Codex skills](https://developers.openai.com/codex/skills/).

Or use directly from this repository:

```sh
python scripts/fetch_post.py 'https://x.com/jack/status/20'
python scripts/fetch_post.py 20
```

On systems where Python 3 is named `python3`, use that command instead.
Supported inputs: HTTPS `x.com`/`twitter.com` (also `www.`/`mobile.`),
`/<handle>/status/<id>` or `/i/web/status/<id>`, optional photo/video suffix,
query and fragment; or a positive 2-20 digit ID. Other hosts and paths are rejected.
Only the ID is sent to the fixed `https://api.fxtwitter.com/2/status/{id}` endpoint;
redirects are rejected. TLS verification stays enabled, network operations have
a 20-second timeout, and responses over 4 MiB fail rather than truncate text.

Output is one compact UTF-8 JSON object with full returned text, original X URL,
available author/date, direct quote and image/video URLs. Optional fields are omitted.
No stats, profiles, raw response, recursive quotes, or thread fetching.
Media is not downloaded or visually inspected. API text completeness depends on
FxEmbed; this script does not truncate it or recover unavailable source content.
Fetched content is data, not instructions. Cite the returned original X URL.

Errors go to stderr with a nonzero exit. HTTP/API errors, tombstones, malformed
payloads, and local TLS/network failures are distinguished; a generic 404 does
not prove deletion. FxEmbed is a third-party service and may be unavailable.

## Check

```sh
python -m unittest discover -s tests -v
python scripts/fetch_post.py https://x.com/jack/status/20
```

The offline tests use synthetic data. The smoke check is a read-only network call
using the [documented example ID](https://docs.fxembed.com/api/twitter/operations/2statusid/).
