<script>
  export let step;
  export let index;

  function formatSelectionEvent(sel) {
    if (!sel) return '';
    const type = sel.type ?? 'unknown';
    if (type === 'alternatives') {
      const count = sel.alternatives?.length ?? 0;
      return `Found ${count} alternative${count !== 1 ? 's' : ''} for "${sel.query ?? '?'}"`;
    }
    if (type === 'select') {
      const label = sel.label ?? sel.identifier ?? '?';
      const variant = sel.variant ? ` (${sel.variant})` : '';
      return `Selected: ${label}${variant}`;
    }
    if (type === 'validation') {
      return `Validation: ${sel.passed ? 'passed' : 'failed'}`;
    }
    if (type === 'backtrack') {
      return 'Backtracking...';
    }
    if (type === 'continue') {
      return 'Continuing with next alternative...';
    }
    if (type === 'fail') {
      return 'Skeleton failed, trying next...';
    }
    return JSON.stringify(sel);
  }
</script>

<div class="step-card">
  {#if step.type === 'skeletons'}
    <div class="step-header">
      <span class="step-badge step-badge--skeleton">Skeletons</span>
      <span class="step-count">{step.skeletons?.length ?? 0} generated</span>
    </div>
    <div class="skeleton-list">
      {#each step.skeletons ?? [] as skeleton, i (i)}
        <pre class="skeleton-item">{skeleton}</pre>
      {/each}
    </div>
  {:else if step.type === 'selection'}
    <div class="step-header">
      <span class="step-badge step-badge--selection">Selection</span>
      <span class="step-meta">Skeleton #{step.skeleton + 1}</span>
    </div>
    <p class="step-detail">{formatSelectionEvent(step.selection)}</p>
  {:else}
    <div class="step-header">
      <span class="step-badge">Step {index + 1}</span>
    </div>
    <pre class="step-raw">{JSON.stringify(step, null, 2)}</pre>
  {/if}
</div>

<style>
  .step-card {
    padding: var(--spacing-md) var(--spacing-lg);
    background: var(--surface-base);
    display: flex;
    flex-direction: column;
    gap: var(--spacing-sm);
  }

  .step-header {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
  }

  .step-badge {
    display: inline-flex;
    padding: 0.15rem 0.5rem;
    border-radius: var(--radius-sm);
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    background: rgba(0, 0, 0, 0.06);
    color: var(--text-subtle);
  }

  .step-badge--skeleton {
    background: rgba(37, 99, 235, 0.1);
    color: var(--color-accent);
  }

  .step-badge--selection {
    background: rgba(16, 185, 129, 0.1);
    color: #059669;
  }

  .step-count {
    font-size: 0.8rem;
    color: var(--text-subtle);
  }

  .step-meta {
    font-size: 0.8rem;
    color: var(--text-subtle);
  }

  .skeleton-list {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-xs);
  }

  .skeleton-item {
    margin: 0;
    padding: var(--spacing-sm) var(--spacing-md);
    background: #0f172a;
    color: #f8fafc;
    border-radius: var(--radius-sm);
    font-family: 'Fira Code', 'SFMono-Regular', Consolas, monospace;
    font-size: 0.78rem;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-x: auto;
  }

  .step-detail {
    margin: 0;
    font-size: 0.85rem;
    color: var(--text-primary);
  }

  .step-raw {
    margin: 0;
    padding: var(--spacing-sm);
    background: #f8fafc;
    border-radius: var(--radius-sm);
    font-size: 0.78rem;
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
  }
</style>
