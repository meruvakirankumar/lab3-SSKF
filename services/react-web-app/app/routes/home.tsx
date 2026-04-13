import { useMemo, useState } from "react";
import { Link } from "react-router";
import type { Route } from "./+types/home";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import { MermaidDiagram } from "~/components/MermaidDiagram";

type ProjectStatus = "pending" | "analyzing" | "complete" | "failed";

type LanguageInfo = {
  name: string;
  file_count: number;
  line_count: number;
  percentage: number;
  color: string;
};

type Project = {
  id: string;
  project_name: string;
  upload_timestamp: string;
  zip_filename: string;
  file_size_bytes: number;
  status: ProjectStatus;
  error_message?: string | null;
  languages?: LanguageInfo[];
  frameworks?: string[];
  primary_language?: string;
  total_files_analyzed?: number;
  total_lines?: number;
};

type Diagram = {
  id: string;
  project_id: string;
  diagram_type: "component" | "class" | "dependency" | "flowchart";
  diagram_format: "mermaid";
  diagram_content: string;
  generated_timestamp: string;
  file_count: number;
  component_count: number;
  ai_enhanced?: boolean;
};

type DataFlow = {
  id: string;
  project_id: string;
  flow_name: string;
  start_component: string;
  end_component: string;
  steps: string[];
  description?: string;
};

type AIInsights = {
  architecture_pattern?: string;
  main_components?: string[];
  key_responsibilities?: Record<string, string>;
  data_flows?: Array<{ name: string; start: string; end: string; steps: string[]; description: string }>;
  dependencies?: string[];
  technologies?: string[];
  quality_assessment?: string;
};

type ApiResponse<T> = {
  success: boolean;
  data?: T;
  error?: string;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:3030";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Code Architecture Analyzer" },
    { name: "description", content: "Upload a codebase zip and generate architecture and data-flow diagrams." },
  ];
}

export default function Home() {
  const [projectName, setProjectName] = useState("");
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [diagrams, setDiagrams] = useState<Diagram[]>([]);
  const [flows, setFlows] = useState<DataFlow[]>([]);
  const [aiInsights, setAiInsights] = useState<AIInsights | null>(null);

  const statusTone = useMemo(() => {
    if (!project) return "secondary" as const;
    if (project.status === "complete") return "default" as const;
    if (project.status === "failed") return "destructive" as const;
    return "secondary" as const;
  }, [project]);

  async function uploadAndAnalyze() {
    if (!zipFile) {
      setError("Please select a zip file first");
      return;
    }
    await handleFileSelected(zipFile);
  }

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFiles = e.dataTransfer.files;
    if (droppedFiles && droppedFiles.length > 0) {
      const file = droppedFiles[0];
      if (file.name.toLowerCase().endsWith(".zip")) {
        setZipFile(file);
        setError("");
        // Automatically start upload and analysis
        handleFileSelected(file);
      } else {
        setError("Please drop a .zip file");
      }
    }
  };

  const handleFileSelected = async (file: File) => {
    // Generate project name from filename if not provided
    const generatedName = projectName.trim() || file.name.replace(".zip", "");
    
    setLoading(true);
    setError("");
    setProject(null);
    setDiagrams([]);
    setFlows([]);
    setAiInsights(null);

    try {
      const formData = new FormData();
      formData.append("project_name", generatedName);
      formData.append("file", file);

      console.log("Auto-uploading file:", file.name, "to", `${API_BASE}/api/upload`);

      const uploadResponse = await fetch(`${API_BASE}/api/upload`, {
        method: "POST",
        body: formData,
      });

      console.log("Upload response status:", uploadResponse.status);
      
      const uploadJson = (await uploadResponse.json()) as ApiResponse<Project>;
      console.log("Upload response data:", uploadJson);
      
      if (!uploadResponse.ok || !uploadJson.success || !uploadJson.data) {
        throw new Error(uploadJson.error ?? `Upload failed: ${uploadResponse.status}`);
      }

      console.log("Project created:", uploadJson.data.id);
      setProject(uploadJson.data);

      console.log("Starting analysis for project:", uploadJson.data.id);
      const analyzeResponse = await fetch(`${API_BASE}/api/projects/${uploadJson.data.id}/analyze`, {
        method: "POST",
      });
      
      console.log("Analyze response status:", analyzeResponse.status);
      
      const analyzeJson = (await analyzeResponse.json()) as ApiResponse<Project>;
      console.log("Analyze response data:", analyzeJson);
      
      if (!analyzeResponse.ok || !analyzeJson.success || !analyzeJson.data) {
        throw new Error(analyzeJson.error ?? `Analysis failed: ${analyzeResponse.status}`);
      }

      setProject(analyzeJson.data);

      console.log("Fetching diagrams and dataflows...");
      const [diagramRes, flowRes, insightsRes] = await Promise.all([
        fetch(`${API_BASE}/api/projects/${uploadJson.data.id}/diagrams`),
        fetch(`${API_BASE}/api/projects/${uploadJson.data.id}/dataflows`),
        fetch(`${API_BASE}/api/projects/${uploadJson.data.id}/insights`).catch(() => null),
      ]);

      const diagramsJson = (await diagramRes.json()) as ApiResponse<Diagram[]>;
      const flowsJson = (await flowRes.json()) as ApiResponse<DataFlow[]>;
      
      console.log("Diagrams response:", diagramsJson);
      console.log("Diagrams count:", diagramsJson.data?.length);
      if (diagramsJson.data && diagramsJson.data.length > 0) {
        console.log("First diagram:", diagramsJson.data[0]);
        console.log("First diagram content length:", diagramsJson.data[0].diagram_content?.length);
        console.log("First diagram content:", diagramsJson.data[0].diagram_content?.substring(0, 200));
      }
      console.log("Flows:", flowsJson.data?.length);
      
      setDiagrams(diagramsJson.data ?? []);
      setFlows(flowsJson.data ?? []);
      
      if (insightsRes && insightsRes.ok) {
        const insightsJson = (await insightsRes.json()) as ApiResponse<AIInsights>;
        console.log("AI Insights:", insightsJson.data);
        setAiInsights(insightsJson.data ?? null);
      }
      
      console.log("✓ Analysis complete!");
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unexpected error";
      console.error("Error:", message, e);
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_20%_20%,hsl(45_95%_85%),transparent_40%),radial-gradient(circle_at_90%_0%,hsl(200_90%_88%),transparent_35%),linear-gradient(180deg,hsl(30_30%_98%),hsl(35_25%_94%))] p-6 md:p-10">
      <section className="mx-auto max-w-6xl">
        <Card className="border-amber-200/70 shadow-xl shadow-amber-950/5">
          <CardHeader>
            <CardTitle className="text-3xl md:text-4xl tracking-tight">Code Architecture Analyzer</CardTitle>
            <CardDescription>Upload a repository zip and get component, class, and dependency diagrams.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 md:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-4 rounded-xl border bg-card p-4">
              <label className="block space-y-2">
                <span className="text-sm font-medium">Project name <span className="text-xs text-muted-foreground">(optional)</span></span>
                <Input 
                  value={projectName} 
                  onChange={(e) => setProjectName(e.target.value)} 
                  placeholder="Leave empty to use filename" 
                  disabled={loading}
                />
              </label>

              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={`relative rounded-lg border-2 border-dashed p-8 text-center transition-all ${
                  isDragging
                    ? "border-primary bg-primary/5 shadow-md"
                    : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/30"
                }`}
              >
                <label className="cursor-pointer block">
                  <div className="space-y-2">
                    <div className="text-4xl">📁</div>
                    <p className="text-sm font-medium">Drag and drop your .zip file here</p>
                    <p className="text-xs text-muted-foreground">or click to browse</p>
                    <p className="text-xs text-muted-foreground">Max file size: 2 GB</p>
                  </div>
                  <input
                    type="file"
                    accept=".zip"
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      if (file && file.name.toLowerCase().endsWith(".zip")) {
                        console.log("File selected via input:", file.name);
                        setZipFile(file);
                        setError("");
                        // Automatically start upload and analysis
                        handleFileSelected(file);
                      } else if (file) {
                        setError("Please select a .zip file");
                      }
                    }}
                    className="hidden"
                  />
                </label>
              </div>

              {zipFile && (
                <div className="rounded-lg bg-blue-50 p-3 text-sm border border-blue-200">
                  <p className="font-medium text-blue-900">📊 Auto-analyzing...</p>
                  <p className="text-blue-700 text-xs">{zipFile.name}</p>
                  {loading && <p className="text-blue-600 text-xs mt-2">Processing your codebase with AI...</p>}
                </div>
              )}

              {!loading && zipFile && (
                <Button 
                  onClick={uploadAndAnalyze} 
                  variant="outline"
                  className="w-full"
                >
                  Re-analyze
                </Button>
              )}

              {loading && (
                <Button 
                  disabled
                  className="w-full"
                >
                  <span className="flex items-center justify-center gap-2">
                    <span className="animate-spin">⚙️</span>
                    Uploading & Analyzing...
                  </span>
                </Button>
              )}
              {error ? <p className="text-sm text-destructive bg-red-50 p-2 rounded">{error}</p> : null}
            </div>

            <div className="rounded-xl border bg-card p-4 space-y-3">
              <h2 className="text-lg font-semibold">Project status</h2>
              {project ? (
                <>
                  <p className="text-sm text-muted-foreground">{project.project_name}</p>
                  <p className="text-sm text-muted-foreground">{project.zip_filename}</p>
                  <Badge variant={statusTone}>{project.status}</Badge>
                  {project.error_message ? <p className="text-sm text-destructive">{project.error_message}</p> : null}

                  {/* Language breakdown */}
                  {project.languages && project.languages.length > 0 && (
                    <div className="mt-3 pt-3 border-t space-y-2">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Languages</p>
                      {/* Color bar */}
                      <div className="flex h-2 rounded-full overflow-hidden gap-[2px]">
                        {project.languages.map((lang) => (
                          <div
                            key={lang.name}
                            style={{ width: `${lang.percentage}%`, backgroundColor: lang.color }}
                            title={`${lang.name}: ${lang.percentage}%`}
                            className="transition-all"
                          />
                        ))}
                      </div>
                      {/* Legend */}
                      <div className="flex flex-wrap gap-x-3 gap-y-1">
                        {project.languages.map((lang) => (
                          <div key={lang.name} className="flex items-center gap-1 text-xs">
                            <span className="w-2.5 h-2.5 rounded-full inline-block flex-shrink-0" style={{ backgroundColor: lang.color }} />
                            <span className="font-medium">{lang.name}</span>
                            <span className="text-muted-foreground">{lang.percentage}%</span>
                          </div>
                        ))}
                      </div>
                      {/* Stats */}
                      {project.total_files_analyzed != null && (
                        <p className="text-xs text-muted-foreground">
                          {project.total_files_analyzed} files · {(project.total_lines ?? 0).toLocaleString()} lines
                        </p>
                      )}
                    </div>
                  )}

                  {/* Frameworks */}
                  {project.frameworks && project.frameworks.length > 0 && (
                    <div className="space-y-1">
                      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Frameworks & Tools</p>
                      <div className="flex flex-wrap gap-1">
                        {project.frameworks.map((fw) => (
                          <Badge key={fw} variant="outline" className="text-xs">🔧 {fw}</Badge>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {aiInsights && (
                    <div className="mt-4 pt-4 border-t space-y-2">
                      <h3 className="font-semibold text-sm">🤖 AI Insights</h3>
                      {aiInsights.architecture_pattern && (
                        <div className="text-sm">
                          <span className="font-medium">Pattern:</span> {aiInsights.architecture_pattern}
                        </div>
                      )}
                      {aiInsights.main_components && aiInsights.main_components.length > 0 && (
                        <div className="text-sm">
                          <span className="font-medium">Components:</span>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {aiInsights.main_components.map((comp) => (
                              <Badge key={comp} variant="outline" className="text-xs">{comp}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {aiInsights.technologies && aiInsights.technologies.length > 0 && (
                        <div className="text-sm">
                          <span className="font-medium">Tech:</span>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {aiInsights.technologies.slice(0, 4).map((tech) => (
                              <Badge key={tech} variant="outline" className="text-xs">{tech}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {aiInsights.quality_assessment && (
                        <div className="text-sm">
                          <span className="font-medium">Quality:</span>
                          <p className="text-xs text-muted-foreground mt-1">{aiInsights.quality_assessment}</p>
                        </div>
                      )}
                    </div>
                  )}
                  
                  {project.status === "complete" && (
                    <Link to={`/architecture/${project.id}`} className="w-full">
                      <Button className="w-full mt-4" variant="default">
                        📊 View Complete Architecture
                      </Button>
                    </Link>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">No project analyzed yet.</p>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Architecture diagrams</CardTitle>
              <CardDescription>Mermaid output generated from imports and exported symbols.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {diagrams.length === 0 ? (
                <p className="text-sm text-muted-foreground">No diagrams yet.</p>
              ) : (
                diagrams.map((diagram) => (
                  <article key={diagram.id} className="space-y-2 rounded-lg border p-3">
                    <div className="flex items-center justify-between">
                      <h3 className="font-medium capitalize">{diagram.diagram_type}</h3>
                      <Badge variant="secondary">{diagram.file_count} files</Badge>
                    </div>
                    <MermaidDiagram 
                      content={diagram.diagram_content} 
                      className="mt-3"
                    />
                  </article>
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Data flows</CardTitle>
              <CardDescription>Detected start-to-end flow across code components.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {flows.length === 0 ? (
                <p className="text-sm text-muted-foreground">No flows yet.</p>
              ) : (
                flows.map((flow) => (
                  <article key={flow.id} className="rounded-lg border p-3">
                    <h3 className="font-medium">{flow.flow_name}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {flow.start_component} {"->"} {flow.end_component}
                    </p>
                    {flow.steps.length > 0 ? (
                      <ul className="mt-2 list-disc pl-5 text-sm text-muted-foreground">
                        {flow.steps.map((step) => (
                          <li key={step}>{step}</li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    </main>
  );
}
