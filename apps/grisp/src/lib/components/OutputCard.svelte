<script>
  import SparqlBlock from './SparqlBlock.svelte';

  export let output;

  const out = output?.output ?? {};
  const elapsed = typeof output?.elapsed === 'number' ? output.elapsed : null;
  const error = output?.error ?? null;

  const sparql = out?.sparql ?? null;
  const selections = out?.selections ?? null;
  const result = out?.result ?? null;
  const formatted = out?.formatted ?? null;
  const endpoint = out?.endpoint ?? null;
</script>

<div class="output-card">
  <div class="output-header">
    <h2 class="output-title">Output</h2>
    {#if elapsed !== null}
      <span class="chip">{elapsed.toFixed(2)}s</span>
    {/if}
  </div>

  {#if error}
    <div class="error-block">
      <p class="error-reason">Error: {error.reason ?? 'unknown'}</p>
      {#if error.content}
        <pre class="error-content">{error.content}</pre>
      {/if}
    </div>
  {/if}

  {#if sparql}
    <SparqlBlock code={sparql} {endpoint} />
  {/if}

  {#if selections}
    <div class="section">
      <h3 class="section-title">Selections</h3>
      <pre class="pre-block">{selections}</pre>
    </div>
  {/if}

  {#if result}
    <div class="section">
      <h3 class="section-title">Result</h3>
      <pre class="pre-block">{result}</pre>
    </div>
  {/if}

  {#if !sparql && !error}
    <p class="placeholder">No SPARQL query generated.</p>
  {/if}
</div>

<style>
  .output-card {
    border: 1px solid var(--color-accent-border);
    border-radius: var(--radius-md);
    background: var(--surface-base);
    padding: var(--spacing-lg);
    display: flex;
    flex-direction: column;
    gap: var(--spacing-md);
    box-shadow: var(--shadow-sm);
  }

  .output-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .output-title {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--color-accent-dark);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    background: var(--color-accent-light);
    color: var(--color-accent);
    font-size: 0.75rem;
    font-weight: 600;
  }

  .error-block {
    padding: var(--spacing-md);
    background: rgba(239, 68, 68, 0.06);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: var(--radius-sm);
  }

  .error-reason {
    margin: 0;
    font-weight: 600;
    color: #dc2626;
    font-size: 0.9rem;
  }

  .error-content {
    margin: var(--spacing-xs) 0 0;
    font-size: 0.85rem;
    white-space: pre-wrap;
    word-break: break-word;
    color: #7f1d1d;
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
  }

  .section-title {
    margin: 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-subtle);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .pre-block {
    margin: 0;
    padding: var(--spacing-md);
    background: #f8fafc;
    border: 1px solid var(--border-default);
    border-radius: var(--radius-sm);
    font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace;
    font-size: 0.82rem;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-x: auto;
    max-height: 300px;
    overflow-y: auto;
  }

  .placeholder {
    margin: 0;
    color: var(--text-subtle);
    font-size: 0.9rem;
    font-style: italic;
  }
</style>
