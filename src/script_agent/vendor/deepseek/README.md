# DeepSeek reference assets

These unmodified files come from the official `deepseek-ai/DeepSeek-V4.1-Flash-1017`
Hugging Face repository at revision `1bae0e1088993b9b82de08f59de5be5a34e42170`:

- `encoding.py`: reference conversation renderer, including tools and thinking mode.
- `tokenizer.json`: ByteLevel BPE tokenizer, loaded locally by `tokenizers`.
- `LICENSE`: upstream MIT license, retained in full.

`provenance.json` records the exact download URLs, byte sizes, and SHA-256 hashes.
The reference encoder was inspected before use; its imports are only Python's
`typing`, `copy`, `json`, and `re`. The application calls `encode_messages` only;
it does not call the upstream file-loading helper or download anything at runtime.

The cloud service can evolve independently of this reference. Local counting is
a **preflight estimate**, not the provider's authoritative usage or an enforced
server context limit. The application counts the full rendered prompt and the
serialized request, takes the larger count, adds a 10% + 128 token allowance, and
reserves the requested maximum output. It never truncates source text to pass.

Official references:

- https://api-docs.deepseek.com/quick_start/token_usage/
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017
