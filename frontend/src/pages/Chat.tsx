import { type FormEvent, useState } from 'react';
import { api, type ChatResponse } from '../api/client';
import ChatMarkdown from '../components/ChatMarkdown';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  evidence?: ChatResponse['evidence'];
  mode?: string;
  suggested_queries?: string[];
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content:
        '## Welcome\n\nI search your **live crime database** and answer in plain language.\n\n**Try asking:**\n- Crimes in Bangalore\n- How many records are loaded?\n- Summarize recent FIRs',
      mode: 'local',
    },
  ]);
  const [input, setInput] = useState('');
  const [language, setLanguage] = useState('en');
  const [loading, setLoading] = useState(false);

  function appendMessage(response: ChatResponse) {
    setMessages((prev) => [
      ...prev,
      {
        role: 'assistant',
        content: response.reply,
        evidence: response.evidence,
        mode: response.mode,
        suggested_queries: response.suggested_queries,
      },
    ]);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    const historyForApi = [
      ...messages.filter((m) => m.role === 'user' || m.role === 'assistant'),
      { role: 'user' as const, content: userMessage },
    ];
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const response = await api.chat(
        userMessage,
        language,
        historyForApi.slice(-10).map((m) => ({ role: m.role, content: m.content })),
      );
      appendMessage(response);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            '## Error\n\nCould not reach the intelligence service. Ensure the **backend** is running on port 8000.',
          mode: 'local',
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function askSuggestion(query: string) {
    setInput(query);
  }

  return (
    <div className="page chat-page">
      <header className="page-header">
        <div>
          <h2>Intelligence Chat</h2>
          <p>Answers grounded in your uploaded FIRs — English & Kannada</p>
        </div>
        <select value={language} onChange={(e) => setLanguage(e.target.value)} className="lang-select">
          <option value="en">English</option>
          <option value="kn">Kannada</option>
        </select>
      </header>

      <div className="chat-container panel">
        <div className="chat-messages">
          {messages.map((msg, i) => (
            <div key={i} className={`chat-bubble ${msg.role}`}>
              {msg.role === 'assistant' ? (
                <>
                  {msg.mode && (
                    <span className={`chat-mode-badge ${msg.mode}`}>
                      {msg.mode === 'llm' ? 'AI analysis' : 'Database search'}
                    </span>
                  )}
                  <ChatMarkdown content={msg.content} />
                </>
              ) : (
                <p className="chat-user-text">{msg.content}</p>
              )}

              {msg.evidence && msg.evidence.length > 0 && (
                <div className="evidence-trail">
                  <strong>Sources</strong>
                  <ul>
                    {msg.evidence.map((e, j) => (
                      <li key={j}>
                        <span className="evidence-source">{e.source}</span> {e.detail}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {msg.suggested_queries && msg.suggested_queries.length > 0 && (
                <div className="chat-suggestions">
                  <span className="chat-suggestions-label">Follow up</span>
                  <div className="chat-suggestion-chips">
                    {msg.suggested_queries.map((q) => (
                      <button
                        key={q}
                        type="button"
                        className="chat-suggestion-chip"
                        onClick={() => askSuggestion(q)}
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="chat-bubble assistant">
              <span className="chat-mode-badge llm">Analyzing</span>
              <p className="chat-loading-text">Searching records and preparing briefing…</p>
            </div>
          )}
        </div>

        <form onSubmit={handleSubmit} className="chat-input-row">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask anything about your crime records..."
          />
          <button type="submit" disabled={loading}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
