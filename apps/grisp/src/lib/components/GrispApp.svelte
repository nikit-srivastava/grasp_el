<script>
  import { onMount, onDestroy } from 'svelte';
  import { wsEndpoint, kgEndpoint } from '../constants.js';
  import StepCard from './StepCard.svelte';
  import OutputCard from './OutputCard.svelte';
  import SparqlBlock from './SparqlBlock.svelte';

  let question = '';
  let connectionStatus = 'initial';
  let statusMessage = '';
  let running = false;
  let cancelling = false;
  let socket;
  let kg = '';

  // generation state
  let steps = [];
  let output = null;
  let error = null;
  let pendingCancelSignal = false;

  $: connected = connectionStatus === 'connected';
  $: canSubmit = connected && !running && question.trim().length > 0;
  $: hasSteps = steps.length > 0;
  $: hasOutput = output !== null;
  $: hasResult = hasSteps || hasOutput || error !== null;

  onMount(async () => {
    await initialize();
  });

  onDestroy(() => {
    cleanupSocket();
  });

  async function initialize() {
    try {
      await loadKnowledgeGraph();
      await openConnection();
    } catch (err) {
      console.error('Failed to initialize', err);
      statusMessage = 'Failed to initialize. Please check your connection and reload.';
    }
  }

  async function loadKnowledgeGraph() {
    const response = await fetch(kgEndpoint());
    if (!response.ok) throw new Error('Failed to load knowledge graph info');
    const kgs = await response.json();
    if (Array.isArray(kgs) && kgs.length > 0) {
      kg = kgs[0];
    }
  }

  async function openConnection() {
    cleanupSocket();
    connectionStatus = 'connecting';
    return new Promise((resolve, reject) => {
      try {
        socket = new WebSocket(wsEndpoint());
      } catch (err) {
        connectionStatus = 'error';
        return reject(err);
      }

      socket.addEventListener('open', () => {
        connectionStatus = 'connected';
        statusMessage = '';
        resolve();
      });

      socket.addEventListener('message', handleSocketMessage);
      socket.addEventListener('close', handleSocketClose);
      socket.addEventListener('error', () => {
        connectionStatus = 'error';
        statusMessage = 'WebSocket error occurred.';
        reject(new Error('WebSocket error'));
      });
    });
  }

  function cleanupSocket() {
    if (socket) {
      socket.removeEventListener('message', handleSocketMessage);
      socket.removeEventListener('close', handleSocketClose);
      socket.close();
      socket = null;
    }
  }

  function handleSocketClose(event) {
    connectionStatus = 'disconnected';
    running = false;
    cancelling = false;
    pendingCancelSignal = false;
    statusMessage = event?.reason || 'Connection lost. Please reload to reconnect.';
  }

  function handleSocketMessage(event) {
    try {
      const payload = JSON.parse(event.data);

      if (payload.error && !payload.type) {
        statusMessage = payload.error;
        running = false;
        cancelling = false;
        sendAck();
        return;
      }

      if (payload.cancelled) {
        running = false;
        cancelling = false;
        return;
      }

      if (!payload.type) {
        sendAck();
        return;
      }

      if (payload.type === 'skeletons') {
        steps = [...steps, { type: 'skeletons', skeletons: payload.skeletons }];
      } else if (payload.type === 'selection') {
        steps = [...steps, {
          type: 'selection',
          skeleton: payload.skeleton,
          selection: payload.selection,
        }];
      } else if (payload.type === 'output') {
        output = payload;
        running = false;
        cancelling = false;
        pendingCancelSignal = false;
      }

      sendAck();
    } catch (err) {
      console.error('Failed to handle message', err);
    }
  }

  function sendAck() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    const payload = { received: true };
    if (pendingCancelSignal) {
      payload.cancel = true;
      pendingCancelSignal = false;
    }
    socket.send(JSON.stringify(payload));
  }

  function handleSubmit() {
    if (!canSubmit) return;

    statusMessage = '';
    error = null;
    steps = [];
    output = null;
    running = true;

    try {
      socket?.send(JSON.stringify({ question: question.trim() }));
    } catch (err) {
      statusMessage = 'Failed to send request.';
      running = false;
    }
  }

  function handleCancel() {
    if (!connected) return;
    cancelling = true;
    pendingCancelSignal = true;
  }

  function handleReset() {
    question = '';
    steps = [];
    output = null;
    error = null;
    statusMessage = '';
  }

  function handleKeydown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }
</script>

<section class="app-shell">
  <header class="header">
    <h1 class="title">GRISP</h1>
    <p class="subtitle">
      Grammar-Regulated Interactive SPARQL generation with Phrase alternatives
      {#if kg}
        <span class="kg-badge">{kg}</span>
      {/if}
    </p>
  </header>

  <main class="main-content" class:main-content--centered={!hasResult}>
    <!-- Input -->
    <div class="input-section">
      <div class="input-row">
        <input
          class="question-input"
          type="text"
          placeholder={connected ? 'Ask a question...' : 'Connecting...'}
          bind:value={question}
          on:keydown={handleKeydown}
          disabled={!connected || running}
        />
        <div class="button-group">
          {#if running}
            <button
              class="btn btn--cancel"
              on:click={handleCancel}
              disabled={cancelling}
            >
              {cancelling ? 'Cancelling...' : 'Cancel'}
            </button>
          {:else}
            <button
              class="btn btn--submit"
              on:click={handleSubmit}
              disabled={!canSubmit}
            >
              Generate
            </button>
          {/if}
          {#if hasResult && !running}
            <button class="btn btn--reset" on:click={handleReset}>
              Clear
            </button>
          {/if}
        </div>
      </div>

      {#if statusMessage}
        <p class="status-message">{statusMessage}</p>
      {/if}

      {#if connectionStatus === 'disconnected' || connectionStatus === 'error'}
        <button class="btn btn--reload" on:click={() => window.location.reload()}>
          Reload
        </button>
      {/if}
    </div>

    <!-- Progress -->
    {#if running && !hasOutput}
      <div class="progress-section">
        <div class="progress-bar">
          <span class="spinner" aria-hidden="true"></span>
          <span class="progress-text">
            {#if steps.length === 0}
              Generating skeletons...
            {:else if steps.some(s => s.type === 'skeletons') && !steps.some(s => s.type === 'selection')}
              Starting selection...
            {:else}
              Selecting IRIs (skeleton {(steps.filter(s => s.type === 'selection').slice(-1)[0]?.skeleton ?? 0) + 1})...
            {/if}
          </span>
        </div>
      </div>
    {/if}

    <!-- Output -->
    {#if hasOutput}
      <OutputCard {output} />
    {/if}

    <!-- Intermediate steps -->
    {#if hasSteps}
      <details class="steps-section" open={!hasOutput}>
        <summary class="steps-summary">
          Intermediate Steps ({steps.length})
        </summary>
        <div class="steps-list">
          {#each steps as step, i (i)}
            <StepCard {step} index={i} />
          {/each}
        </div>
      </details>
    {/if}
  </main>

  <footer class="footer">
    <p>&copy; {new Date().getFullYear()} University of Freiburg</p>
  </footer>
</section>

<style>
  .app-shell {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    padding: 12px 12px 0;
    margin: 0 auto;
    width: min(100%, 800px);
    gap: var(--spacing-lg);
  }

  .header {
    text-align: center;
    padding: var(--spacing-lg) 0 0;
  }

  .title {
    margin: 0;
    font-size: 2rem;
    font-weight: 700;
    color: var(--color-accent-dark);
    letter-spacing: -0.02em;
  }

  .subtitle {
    margin: var(--spacing-xs) 0 0;
    color: var(--text-subtle);
    font-size: 0.9rem;
  }

  .kg-badge {
    display: inline-flex;
    align-items: center;
    padding: 0.1rem 0.5rem;
    background: var(--color-accent-light);
    border: 1px solid var(--color-accent-border);
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--color-accent);
    margin-left: var(--spacing-xs);
  }

  .main-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--spacing-lg);
  }

  .main-content--centered {
    justify-content: center;
  }

  .input-section {
    display: flex;
    flex-direction: column;
    gap: var(--spacing-sm);
  }

  .input-row {
    display: flex;
    gap: var(--spacing-sm);
    align-items: stretch;
  }

  .question-input {
    flex: 1;
    padding: 0.6rem 0.85rem;
    border: 1px solid var(--color-accent-border);
    border-radius: var(--radius-md);
    font-size: 0.95rem;
    font-family: inherit;
    background: var(--surface-base);
    color: var(--text-primary);
    outline: none;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }

  .question-input:focus {
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
  }

  .question-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .button-group {
    display: flex;
    gap: var(--spacing-xs);
  }

  .btn {
    padding: 0.55rem 1rem;
    border: none;
    border-radius: var(--radius-md);
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
    white-space: nowrap;
  }

  .btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  .btn:not(:disabled):hover {
    transform: translateY(-1px);
  }

  .btn--submit {
    background: var(--color-accent);
    color: #fff;
  }

  .btn--submit:not(:disabled):hover {
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
  }

  .btn--cancel {
    background: #ef4444;
    color: #fff;
  }

  .btn--reset {
    background: rgba(0, 0, 0, 0.06);
    color: var(--text-subtle);
    border: 1px solid var(--border-default);
  }

  .btn--reload {
    align-self: flex-start;
    background: var(--color-accent-light);
    color: var(--color-accent);
    border: 1px solid var(--color-accent-border);
  }

  .status-message {
    margin: 0;
    font-size: 0.85rem;
    color: #ef4444;
  }

  .progress-section {
    display: flex;
    justify-content: center;
    padding: var(--spacing-lg);
  }

  .progress-bar {
    display: inline-flex;
    align-items: center;
    gap: var(--spacing-sm);
    padding: 0.5rem 1rem;
    background: var(--color-accent-light);
    border: 1px solid var(--color-accent-border);
    border-radius: var(--radius-md);
    color: var(--color-accent);
    font-weight: 600;
    font-size: 0.9rem;
  }

  .progress-text {
    min-width: 0;
  }

  .spinner {
    width: 1rem;
    height: 1rem;
    border-radius: 999px;
    border: 2.5px solid rgba(37, 99, 235, 0.25);
    border-top-color: var(--color-accent);
    animation: spin 0.9s linear infinite;
    flex-shrink: 0;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  .steps-section {
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    background: var(--surface-base);
    overflow: hidden;
  }

  .steps-summary {
    padding: var(--spacing-md) var(--spacing-lg);
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--text-subtle);
    cursor: pointer;
    user-select: none;
  }

  .steps-summary:hover {
    background: rgba(0, 0, 0, 0.02);
  }

  .steps-list {
    display: grid;
    gap: 1px;
    background: var(--border-default);
  }

  .footer {
    text-align: center;
    padding: var(--spacing-sm) 0;
    color: var(--text-subtle);
    font-size: 0.75rem;
  }

  .footer p {
    margin: 0;
  }
</style>
