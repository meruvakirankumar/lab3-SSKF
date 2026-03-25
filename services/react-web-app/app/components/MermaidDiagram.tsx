import { useEffect, useRef, useState } from 'react';

interface MermaidDiagramProps {
  content: string;
  title?: string;
  className?: string;
}

export function MermaidDiagram({ content, title, className = '' }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [isMounted, setIsMounted] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isMounted) return;

    const renderDiagram = async () => {
      if (!content || !content.trim()) {
        console.warn('MermaidDiagram: Empty content provided');
        setSvgContent('');
        setError('No diagram content');
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        setError('');
        
        // Dynamically import mermaid to avoid SSR issues
        const mermaidModule = await import('mermaid');
        const mermaid = mermaidModule.default;
        
        console.log('MermaidDiagram: Rendering with content:', content.substring(0, 100) + '...');
        
        // Initialize mermaid with proper config
        mermaid.initialize({ 
          startOnLoad: false, 
          theme: 'dark', 
          securityLevel: 'loose'
        });
        
        const id = `diagram-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
        console.log('MermaidDiagram: Generated ID:', id);
        
        try {
          const { svg } = await mermaid.render(id, content);
          console.log('MermaidDiagram: Successfully rendered SVG, length:', svg.length);
          setSvgContent(svg);
          setError('');
        } catch (renderErr) {
          throw new Error(`Render failed: ${renderErr instanceof Error ? renderErr.message : String(renderErr)}`);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        console.error('MermaidDiagram: Error:', message);
        console.error('MermaidDiagram: Full error:', err);
        setError(`Failed to render diagram: ${message}`);
        setSvgContent('');
      } finally {
        setIsLoading(false);
      }
    };

    renderDiagram();
  }, [content, isMounted]);

  if (!isMounted) {
    return (
      <div className={className}>
        {title && <h3 className="text-lg font-semibold mb-4 text-slate-200">{title}</h3>}
        <div
          className="bg-slate-900 p-4 rounded-lg border border-slate-700 overflow-auto"
          style={{ minHeight: '300px', maxHeight: '600px' }}
        >
          <div className="text-slate-400 p-4 text-sm">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className={className}>
      {title && <h3 className="text-lg font-semibold mb-4 text-slate-200">{title}</h3>}
      <div className="flex flex-col gap-2">
        {showRaw && (
          <button
            onClick={() => setShowRaw(false)}
            className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded"
          >
            Hide Raw Mermaid
          </button>
        )}
        {!showRaw && (error || !svgContent) && (
          <button
            onClick={() => setShowRaw(true)}
            className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded"
          >
            Show Raw Mermaid Code
          </button>
        )}
      </div>
      <div
        ref={containerRef}
        className="bg-slate-900 p-4 rounded-lg border border-slate-700 overflow-auto flex items-center justify-center"
        style={{ minHeight: '300px', maxHeight: '600px' }}
      >
        {isLoading && !showRaw && (
          <div className="text-slate-400 text-sm">Rendering diagram...</div>
        )}
        {error && !svgContent && !showRaw && (
          <div className="text-yellow-400 text-sm max-h-96 overflow-auto whitespace-pre-wrap break-words p-2">
            {error}
            <p className="mt-2 text-xs text-slate-400">Click "Show Raw Mermaid Code" to see the diagram syntax</p>
          </div>
        )}
        {showRaw && content && (
          <pre className="text-slate-100 text-xs whitespace-pre-wrap break-words w-full overflow-auto">
            {content}
          </pre>
        )}
        {svgContent && !showRaw && !isLoading && (
          <div 
            dangerouslySetInnerHTML={{ __html: svgContent }} 
            className="w-full h-full flex items-center justify-center"
          />
        )}
        {!isLoading && !error && !svgContent && !showRaw && (
          <div className="text-slate-400 text-sm">No diagram content</div>
        )}
      </div>
    </div>
  );
}
