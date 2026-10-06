# Security and privacy

Local Audible is a local, single-user app without authentication. Bind the UI, API, Ollama and speech services to loopback. Do not expose them through public tunnels or run uncoordinated API workers.

Workspace files are sensitive and served to the local client. There is no per-user authorization or encryption at rest. Origin checks do not replace authentication or defend against other local software.

The default Ollama endpoint is local; a remote endpoint receives source text/images. Packages and weights may download from third-party hosts. Upstream model/runtime code executes locally; review it and keep dependencies patched. Process trusted documents. Prompt instructions treat document content as untrusted, but are not infallible defenses.

## Reporting

Never post private source material or credentials in an issue. Use GitHub private vulnerability reporting if enabled; otherwise request a private maintainer contact without sharing sensitive details. Include commit, platform, impact and a synthetic reproduction.

## Publication checklist

- Review all Git history and remote branches, not just the working tree. Ignore rules cannot remove past commits.
- Historical versions of this repository contained book-page images. Do not make the existing repository public until the relevant history/refs and hosting-provider retention concerns are addressed.
- Never force-add data/, book images/, environments, model caches or credentials.
- Use synthetic examples and obtain permission before sharing reference voices or generated samples.
