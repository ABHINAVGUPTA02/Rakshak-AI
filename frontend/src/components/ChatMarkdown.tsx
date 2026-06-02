import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ChatMarkdownProps {
  content: string;
  className?: string;
}

/** Renders assistant replies with GitHub-flavored markdown (bold, lists, headings). */
export default function ChatMarkdown({ content, className = 'chat-markdown' }: ChatMarkdownProps) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="chat-md-p">{children}</p>,
          strong: ({ children }) => <strong className="chat-md-strong">{children}</strong>,
          em: ({ children }) => <em>{children}</em>,
          ul: ({ children }) => <ul className="chat-md-ul">{children}</ul>,
          ol: ({ children }) => <ol className="chat-md-ol">{children}</ol>,
          li: ({ children }) => <li className="chat-md-li">{children}</li>,
          h2: ({ children }) => <h3 className="chat-md-h2">{children}</h3>,
          h3: ({ children }) => <h4 className="chat-md-h3">{children}</h4>,
          code: ({ children }) => <code className="chat-md-code">{children}</code>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="chat-md-link">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
