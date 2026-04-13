import { useEffect, useRef, useState, useCallback, useMemo } from 'react';

const LENS_SIZE = 260;  // diameter of the magnifier circle (px)
const ZOOM      = 3.0;  // magnification factor

interface MermaidDiagramProps {
  content: string;
  title?: string;
  className?: string;
}

interface LensState {
  /** cursor position relative to the container viewport – used to place the lens */
  viewX: number;
  viewY: number;
  /** cursor position relative to the diagram element – used to compute zoom offset */
  diagX: number;
  diagY: number;
}

export function MermaidDiagram({ content, title, className = '' }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const diagramRef   = useRef<HTMLDivElement>(null);   // wraps the rendered SVG
  const [svgContent, setSvgContent] = useState<string>('');
  const [error, setError]           = useState<string>('');
  const [isLoading, setIsLoading]   = useState(true);
  const [isMounted, setIsMounted]   = useState(false);
  const [showRaw, setShowRaw]       = useState(false);
  const [lens, setLens]             = useState<LensState | null>(null);
  const [diagSize, setDiagSize]     = useState({ w: 0, h: 0 });

  useEffect(() => { setIsMounted(true); }, []);

  useEffect(() => {
    if (!isMounted) return;
    const renderDiagram = async () => {
      if (!content || !content.trim()) {
        setSvgContent('');
        setError('No diagram content');
        setIsLoading(false);
        return;
      }
      try {
        setIsLoading(true);
        setError('');
        const mermaidModule = await import('mermaid');
        const mermaid = mermaidModule.default;
        mermaid.initialize({ startOnLoad: false, theme: 'dark', securityLevel: 'loose' });
        const id = `diagram-${Date.now()}-${Math.random().toString(36).substring(2, 11)}`;
        const { svg } = await mermaid.render(id, content);
        setSvgContent(svg);
        setError('');
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setError(`Failed to render diagram: ${message}`);
        setSvgContent('');
      } finally {
        setIsLoading(false);
      }
    };
    renderDiagram();
  }, [content, isMounted]);

  // Measure the natural rendered size of the diagram so the lens copy uses the same dims
  useEffect(() => {
    if (!svgContent || !diagramRef.current) return;
    const rafId = requestAnimationFrame(() => {
      if (diagramRef.current) {
        setDiagSize({
          w: diagramRef.current.scrollWidth,
          h: diagramRef.current.scrollHeight,
        });
      }
    });
    return () => cancelAnimationFrame(rafId);
  }, [svgContent]);

  const handleMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const container = containerRef.current;
    const diagram   = diagramRef.current;
    if (!container || !diagram) return;

    const cRect = container.getBoundingClientRect();
    const dRect = diagram.getBoundingClientRect();

    setLens({
      // where to place the lens circle inside the container
      viewX: e.clientX - cRect.left,
      viewY: e.clientY - cRect.top,
      // exact hit-point inside the diagram element (SVG coordinate space)
      diagX: e.clientX - dRect.left,
      diagY: e.clientY - dRect.top,
    });
  }, []);

  const handleMouseLeave = useCallback(() => setLens(null), []);

  // Strip max-width from Mermaid's inline style so diagrams fill available space
  const displayHtml = useMemo(
    () => svgContent.replace(/max-width\s*:\s*[\d.]+px\s*;?/gi, 'max-width: none;'),
    [svgContent],
  );
  const lensHtml = displayHtml;

  // Position the zoomed SVG inside the lens:
  // (diagX, diagY) in diagram coords → (LENS_SIZE/2, LENS_SIZE/2) in lens coords
  // After scaling by ZOOM, diagram point (diagX, diagY) maps to (diagX*ZOOM, diagY*ZOOM).
  // We need that point at (LENS_SIZE/2, LENS_SIZE/2), so offset the div by:
  const innerLeft = lens ? LENS_SIZE / 2 - lens.diagX * ZOOM : 0;
  const innerTop  = lens ? LENS_SIZE / 2 - lens.diagY * ZOOM : 0;

  // Clamp the lens circle so it stays fully inside the container viewport
  const lensLeft = lens
    ? Math.min(Math.max(lens.viewX - LENS_SIZE / 2, 0), (containerRef.current?.clientWidth  ?? LENS_SIZE) - LENS_SIZE)
    : 0;
  const lensTop  = lens
    ? Math.min(Math.max(lens.viewY - LENS_SIZE / 2, 0), (containerRef.current?.clientHeight ?? LENS_SIZE) - LENS_SIZE)
    : 0;

  if (!isMounted) {
    return (
      <div className={className}>
        {title && <h3 className="text-lg font-semibold mb-4 text-slate-200">{title}</h3>}
        <div className="bg-slate-900 p-4 rounded-lg border border-slate-700" style={{ minHeight: 300 }}>
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
          <button onClick={() => setShowRaw(false)}
            className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded self-start">
            Hide Raw Mermaid
          </button>
        )}
        {!showRaw && (error || !svgContent) && (
          <button onClick={() => setShowRaw(true)}
            className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded self-start">
            Show Raw Mermaid Code
          </button>
        )}
      </div>

      {/* ── diagram container ── */}
      <div
        ref={containerRef}
        onMouseMove={svgContent && !showRaw ? handleMouseMove : undefined}
        onMouseLeave={handleMouseLeave}
        className="relative bg-slate-900 p-4 rounded-lg border border-slate-700 overflow-auto flex items-start justify-center"
        style={{ minHeight: 500, maxHeight: '80vh', cursor: svgContent && !showRaw ? 'crosshair' : 'default' }}
      >
        {isLoading && !showRaw && (
          <div className="text-slate-400 text-sm self-center">Rendering diagram...</div>
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

        {/* ── original diagram ── */}
        {svgContent && !showRaw && !isLoading && (
          <div
            ref={diagramRef}
            dangerouslySetInnerHTML={{ __html: displayHtml }}
            className="w-full flex items-center justify-center"
            style={{ minWidth: 800 }}
          />
        )}

        {!isLoading && !error && !svgContent && !showRaw && (
          <div className="text-slate-400 text-sm self-center">No diagram content</div>
        )}

        {/* ── magnifier lens ── */}
        {lens && svgContent && !showRaw && (
          <div
            aria-hidden="true"
            style={{
              position:      'absolute',
              left:           lensLeft,
              top:            lensTop,
              width:          LENS_SIZE,
              height:         LENS_SIZE,
              borderRadius:  '50%',
              border:        '3px solid #63b3ed',
              boxShadow:     '0 0 0 2px #1e293b, 0 8px 32px rgba(0,0,0,0.75)',
              overflow:      'hidden',
              pointerEvents: 'none',
              background:    '#0f172a',
              zIndex:         50,
            }}
          >
            {/*
              Zoomed copy of the SVG.
              - explicit width/height = natural rendered dims → SVG fills its full size
              - transform: scale(ZOOM) from origin (0,0) magnifies it
              - left/top offsets centre the cursor's diagram point in the lens
            */}
            <div
              dangerouslySetInnerHTML={{ __html: lensHtml }}
              style={{
                position:        'absolute',
                left:             innerLeft,
                top:              innerTop,
                width:            diagSize.w > 0 ? diagSize.w : 1000,
                height:           diagSize.h > 0 ? diagSize.h : 800,
                transformOrigin: '0 0',
                transform:       `scale(${ZOOM})`,
                pointerEvents:   'none',
                flexShrink:       0,
              }}
            />

            {/* crosshair at lens centre */}
            <div style={{ position:'absolute', inset:0, pointerEvents:'none' }}>
              <div style={{ position:'absolute', left:'50%', top:0, bottom:0, width:1, background:'rgba(99,179,237,0.4)', transform:'translateX(-50%)' }} />
              <div style={{ position:'absolute', top:'50%', left:0, right:0, height:1, background:'rgba(99,179,237,0.4)', transform:'translateY(-50%)' }} />
            </div>
          </div>
        )}
      </div>

      {svgContent && !showRaw && (
        <p className="text-xs text-slate-500 mt-1 text-right select-none">
          Hover over the diagram to magnify
        </p>
      )}
    </div>
  );
}


interface MermaidDiagramProps {
  content: string;
  title?: string;
  className?: string;
}


