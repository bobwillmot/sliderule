# Copilot Repository Instructions

## Mandatory chat request logging

For every user chat request in this repository, append one new entry to `summaries/CHAT_SUMMARY.md` before ending your response.

### Logging rules

1. **Append-only**: never rewrite or delete prior entries.
2. **One request = one entry**: log every user request, even if no code changes are made.
3. **Prompt fidelity**: capture the user prompt verbatim when available.
4. **Required fields**: use the existing template fields in `summaries/CHAT_SUMMARY.md`:
   - User Prompt
   - Changes
   - Validation
   - AI Tooling/Models
   - Commit
5. **Timestamp**: use local time in the section header format already used in `summaries/CHAT_SUMMARY.md`.
6. **No duplicates**: do not add duplicate entries for the same request.

If writing fails for any reason, report the failure explicitly and provide the exact entry content that should be appended.