import { type FormEvent, useState } from 'react';
import { api, type ChatResponse } from '../api/client';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  evidence?: ChatResponse['evidence'];
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content:
        'Welcome to Rakshak AI Intelligence Assistant. Ask about crime hotspots, types, networks, or case patterns in English or Kannada.',
    },
  ]);
  const [input, setInput] = useState('');
  const [language, setLanguage] = useState('en');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const response = await api.chat(userMessage, language);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: response.reply, evidence: response.evidence },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Failed to reach the intelligence service. Is the backend running?' },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page chat-page">
      <header className="page-header">
        <div>
          <h2>Intelligence Chat</h2>
          <p>Conversational crime intelligence in English & Kannada</p>
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
              <p>{msg.content}</p>
              {msg.evidence && msg.evidence.length > 0 && (
                <div className="evidence-trail">
                  <strong>Evidence Trail</strong>
                  <ul>
                    {msg.evidence.map((e, j) => (
                      <li key={j}>
                        [{e.source}] {e.detail}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
          {loading && <div className="chat-bubble assistant">Analyzing intelligence data...</div>}
        </div>

        <form onSubmit={handleSubmit} className="chat-input-row">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about hotspots, networks, crime types..."
          />
          <button type="submit" disabled={loading}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
