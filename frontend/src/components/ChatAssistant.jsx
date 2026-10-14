import React, { useState, useRef, useEffect } from 'react';
import { useJourney } from '../context/JourneyContext';
import { sendChatQuery } from '../services/api';
import {
  MessageSquare,
  Send,
  Sparkles,
  Bot,
  User,
  Shield,
  RefreshCw,
  HelpCircle,
  Car,
  Calendar,
  MapPin,
  AlertTriangle,
} from 'lucide-react';

export default function ChatAssistant() {
  const { vehicleType, journeyDate, origin, destination } = useJourney();

  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        `### Welcome to the RouteWise Corridor AI Advisor 👋\n\n` +
        `I provide domain-specific intelligence for the **NH-44 Ramban–Banihal mountain highway** based on the **ST-GNN predictive disruption model**, geophysical road terrain parameters, and verified historical landslide records.\n\n` +
        `I am aware of your current session context:\n` +
        `- **Vehicle Type:** ${vehicleType}\n` +
        `- **Target Date:** ${journeyDate}\n` +
        `- **Planned Route:** ${origin} ➔ ${destination}\n\n` +
        `How can I assist your corridor intelligence analysis today? Choose a suggested question below or type your query.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);

  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sourceEngine, setSourceEngine] = useState('RouteWise Domain Knowledge Engine');
  const [isLiveLLM, setIsLiveLLM] = useState(false);
  const [suggestedPrompts, setSuggestedPrompts] = useState([
    'What are the most dangerous segments between Ramban and Banihal?',
    'Explain the risk on July 9, 2023 (monsoon benchmark).',
    `How does my ${vehicleType} selection affect route vulnerability?`,
    'What is the difference between Low, Medium, and High risk tiers?',
    'How does the ST-GNN model predict road disruptions?',
  ]);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSend = async (messageText) => {
    const textToSend = messageText || input.trim();
    if (!textToSend || isLoading) return;

    const userMsg = {
      role: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);

    try {
      // Build context payload
      const context = {
        selected_date: journeyDate,
        vehicle_type: vehicleType,
        origin,
        destination,
      };

      // History excluding system welcome
      const history = messages.slice(1).map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await sendChatQuery(textToSend, history, context);

      const aiMsg = {
        role: 'assistant',
        content: res.reply,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, aiMsg]);
      setSourceEngine(res.source_engine);
      setIsLiveLLM(res.is_live_llm);

      if (res.suggested_followups && res.suggested_followups.length > 0) {
        setSuggestedPrompts(res.suggested_followups);
      }
    } catch (err) {
      console.error('Chat error:', err);
      const errMsg = {
        role: 'assistant',
        content: `⚠️ **Service Notice:** Unable to reach RouteWise AI service: ${err.message}. Please verify the FastAPI backend connection.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const formatMarkdown = (content) => {
    // Simple fast markdown parser for headers, bold, bullet points, numbers, and code
    const lines = content.split('\n');
    return lines.map((line, idx) => {
      // Headers
      if (line.startsWith('### ')) {
        return <h4 key={idx} className="chat-h4">{line.replace('### ', '')}</h4>;
      }
      if (line.startsWith('## ')) {
        return <h3 key={idx} className="chat-h3">{line.replace('## ', '')}</h3>;
      }
      if (line.startsWith('# ')) {
        return <h2 key={idx} className="chat-h2">{line.replace('# ', '')}</h2>;
      }

      // Bullet points
      if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
        const itemText = line.trim().substring(2);
        return (
          <li key={idx} className="chat-bullet">
            <span dangerouslySetInnerHTML={{ __html: renderInline(itemText) }} />
          </li>
        );
      }

      // Numbered list
      const numMatch = line.trim().match(/^(\d+)\.\s+(.*)/);
      if (numMatch) {
        return (
          <div key={idx} className="chat-numbered-item">
            <span className="chat-num">{numMatch[1]}.</span>
            <span dangerouslySetInnerHTML={{ __html: renderInline(numMatch[2]) }} />
          </div>
        );
      }

      // Blank line
      if (!line.trim()) {
        return <div key={idx} style={{ height: 6 }} />;
      }

      // Normal paragraph
      return (
        <p key={idx} className="chat-p" dangerouslySetInnerHTML={{ __html: renderInline(line) }} />
      );
    });
  };

  const renderInline = (str) => {
    let out = str;
    // Bold
    out = out.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic
    out = out.replace(/\*(.*?)\*/g, '<em>$1</em>');
    // Inline code
    out = out.replace(/`(.*?)`/g, '<code class="chat-code">$1</code>');
    return out;
  };

  return (
    <div className="chat-container">
      {/* Top Header Card */}
      <div className="chat-header-card">
        <div className="chat-header-top">
          <div className="brand-section">
            <div className="brand-icon">
              <Bot size={22} />
            </div>
            <div>
              <h2>RouteWise Conversational AI Assistant</h2>
              <p>Predictive Disruption Reasoning & Corridor Intelligence Interface</p>
            </div>
          </div>

          <div className="system-badges">
            <span className="badge badge-pill" title="Active AI engine">
              <Sparkles size={13} style={{ color: 'var(--accent-secondary)' }} /> {sourceEngine}
            </span>
          </div>
        </div>

        {/* Active Session Context Bar */}
        <div className="chat-context-bar">
          <span style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 600 }}>Active Journey Context:</span>
          <span className="context-pill">
            <Car size={13} /> {vehicleType}
          </span>
          <span className="context-pill">
            <Calendar size={13} /> {journeyDate}
          </span>
          <span className="context-pill">
            <MapPin size={13} /> {origin} ➔ {destination}
          </span>
        </div>
      </div>

      {/* Messages Scroll Area */}
      <div className="chat-messages-box">
        {messages.map((m, idx) => (
          <div key={idx} className={`chat-message-row ${m.role}`}>
            <div className={`chat-avatar ${m.role}`}>
              {m.role === 'assistant' ? <Bot size={18} /> : <User size={18} />}
            </div>
            <div className="chat-bubble-container">
              <div className={`chat-bubble ${m.role}`}>
                {formatMarkdown(m.content)}
              </div>
              <span className="chat-timestamp">{m.timestamp}</span>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="chat-message-row assistant">
            <div className="chat-avatar assistant">
              <Bot size={18} />
            </div>
            <div className="chat-bubble assistant">
              <div className="typing-indicator">
                <RefreshCw size={14} className="spin-icon" style={{ marginRight: 6 }} />
                <span>RouteWise Intelligence analyzing corridor graph & model predictions...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompts Section */}
      <div className="suggested-prompts-bar">
        <span className="suggested-label">
          <HelpCircle size={13} /> Suggested Prompts:
        </span>
        <div className="suggested-chips">
          {suggestedPrompts.map((prompt, idx) => (
            <button
              key={idx}
              type="button"
              className="suggested-chip"
              onClick={() => handleSend(prompt)}
              disabled={isLoading}
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* Chat Input Bar */}
      <div className="chat-input-bar">
        <textarea
          className="chat-textarea"
          placeholder="Ask a question about corridor risk scores, landslide hotspots, travel timing, or model limitations..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={isLoading}
        />
        <button
          type="button"
          className="chat-send-btn"
          onClick={() => handleSend()}
          disabled={!input.trim() || isLoading}
          title="Send message"
        >
          <Send size={16} />
        </button>
      </div>

      {/* Bottom Disclaimer */}
      <div className="chat-footer-disclaimer">
        <AlertTriangle size={12} style={{ display: 'inline', marginRight: 4 }} />
        RouteWise AI delivers advisory reasoning grounded in ERA5 reanalysis and verified historical logs.
        Always consult official Jammu & Kashmir Traffic Police directives for real-time mountain highway clearance.
      </div>
    </div>
  );
}
