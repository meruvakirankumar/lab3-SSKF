import { useEffect, useState } from "react";
import { useParams } from "react-router";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import { MermaidDiagram } from "~/components/MermaidDiagram";

type ProjectStatus = "pending" | "analyzing" | "complete" | "failed";

type Project = {
  id: string;
  project_name: string;
  upload_timestamp: string;
  zip_filename: string;
  file_size_bytes: number;
  status: ProjectStatus;
  error_message?: string | null;
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

export default function Architecture() {
  const { projectId } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [diagrams, setDiagrams] = useState<Diagram[]>([]);
  const [flows, setFlows] = useState<DataFlow[]>([]);
  const [aiInsights, setAiInsights] = useState<AIInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchProjectDetails = async () => {
      if (!projectId) return;

      try {
        setLoading(true);
        const [projectRes, diagramRes, flowRes, insightsRes] = await Promise.all([
          fetch(`${API_BASE}/api/projects/${projectId}`),
          fetch(`${API_BASE}/api/projects/${projectId}/diagrams`),
          fetch(`${API_BASE}/api/projects/${projectId}/dataflows`),
          fetch(`${API_BASE}/api/projects/${projectId}/insights`).catch(() => null),
        ]);

        if (!projectRes.ok) {
          throw new Error("Project not found");
        }

        const projectJson = (await projectRes.json()) as ApiResponse<Project>;
        setProject(projectJson.data ?? null);

        const diagramsJson = (await diagramRes.json()) as ApiResponse<Diagram[]>;
        setDiagrams(diagramsJson.data ?? []);

        const flowsJson = (await flowRes.json()) as ApiResponse<DataFlow[]>;
        setFlows(flowsJson.data ?? []);

        if (insightsRes && insightsRes.ok) {
          const insightsJson = (await insightsRes.json()) as ApiResponse<AIInsights>;
          setAiInsights(insightsJson.data ?? null);
        }
      } catch (e) {
        const message = e instanceof Error ? e.message : "Failed to load project";
        setError(message);
      } finally {
        setLoading(false);
      }
    };

    fetchProjectDetails();
  }, [projectId]);

  if (loading) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6 md:p-10">
        <div className="flex items-center justify-center h-96">
          <div className="text-center space-y-4">
            <div className="text-6xl animate-spin">⚙️</div>
            <p className="text-lg text-muted-foreground">Loading architecture analysis...</p>
          </div>
        </div>
      </main>
    );
  }

  if (error || !project) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6 md:p-10">
        <div className="mx-auto max-w-4xl">
          <Card className="border-red-200 bg-red-50">
            <CardHeader>
              <CardTitle className="text-red-900">Error Loading Project</CardTitle>
            </CardHeader>
            <CardContent className="text-red-800">{error}</CardContent>
          </Card>
          <Button onClick={() => window.history.back()} className="mt-4">
            ← Go Back
          </Button>
        </div>
      </main>
    );
  }

  const diagramsByType = {
    component: diagrams.find((d) => d.diagram_type === "component"),
    class: diagrams.find((d) => d.diagram_type === "class"),
    dependency: diagrams.find((d) => d.diagram_type === "dependency"),
    flowchart: diagrams.find((d) => d.diagram_type === "flowchart"),
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6 md:p-10">
      <section className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-8">
          <Button onClick={() => window.history.back()} variant="outline" className="mb-4">
            ← Back
          </Button>
          <div className="space-y-2">
            <h1 className="text-4xl font-bold text-slate-900">{project.project_name}</h1>
            <p className="text-slate-600">Complete Architecture & Codebase Analysis</p>
          </div>
        </div>

        {/* Project Info */}
        <Card className="mb-8 border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle>Project Information</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <Badge className="mt-1" variant={project.status === "complete" ? "default" : "secondary"}>
                {project.status}
              </Badge>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Zip File</p>
              <p className="font-mono text-sm mt-1">{project.zip_filename}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">File Size</p>
              <p className="text-sm mt-1">{(project.file_size_bytes / 1024).toFixed(2)} KB</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Analyzed</p>
              <p className="text-sm mt-1">{new Date(project.upload_timestamp).toLocaleDateString()}</p>
            </div>
          </CardContent>
        </Card>

        {/* AI Insights */}
        {aiInsights && (
          <Card className="mb-8 border-blue-200 bg-gradient-to-br from-blue-50 to-cyan-50 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                🤖 AI Architecture Insights
              </CardTitle>
              <CardDescription>OpenAI-powered analysis of your codebase</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {aiInsights.architecture_pattern && (
                <div>
                  <h3 className="font-semibold text-slate-900 mb-2">Architecture Pattern</h3>
                  <Badge className="bg-blue-600 text-white text-base px-4 py-2">
                    {aiInsights.architecture_pattern}
                  </Badge>
                </div>
              )}

              {aiInsights.main_components && aiInsights.main_components.length > 0 && (
                <div>
                  <h3 className="font-semibold text-slate-900 mb-3">Main Components</h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {aiInsights.main_components.map((comp) => (
                      <Badge key={comp} variant="outline" className="justify-center py-2">
                        🏗️ {comp}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {aiInsights.key_responsibilities && Object.keys(aiInsights.key_responsibilities).length > 0 && (
                <div>
                  <h3 className="font-semibold text-slate-900 mb-3">Component Responsibilities</h3>
                  <div className="grid gap-3">
                    {Object.entries(aiInsights.key_responsibilities).map(([comp, resp]) => (
                      <div key={comp} className="rounded-lg bg-white p-3 border border-blue-100">
                        <p className="font-medium text-sm text-blue-900">{comp}</p>
                        <p className="text-sm text-slate-600 mt-1">{resp}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {aiInsights.technologies && aiInsights.technologies.length > 0 && (
                <div>
                  <h3 className="font-semibold text-slate-900 mb-3">Technologies Detected</h3>
                  <div className="flex flex-wrap gap-2">
                    {aiInsights.technologies.map((tech) => (
                      <Badge key={tech} variant="secondary" className="bg-cyan-100 text-cyan-900">
                        {tech}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {aiInsights.quality_assessment && (
                <div>
                  <h3 className="font-semibold text-slate-900 mb-2">Quality Assessment</h3>
                  <div className="rounded-lg bg-white p-4 border border-blue-100">
                    <p className="text-slate-700">{aiInsights.quality_assessment}</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Diagrams */}
        <Card className="mb-8 border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle>Architecture Diagrams</CardTitle>
            <CardDescription>Visual representations of your codebase structure</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="component" className="w-full">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="component">Component</TabsTrigger>
                <TabsTrigger value="class">Class</TabsTrigger>
                <TabsTrigger value="dependency">Dependency</TabsTrigger>
                <TabsTrigger value="flowchart">Flowchart</TabsTrigger>
              </TabsList>

              {(["component", "class", "dependency", "flowchart"] as const).map((type) => {
                const diagram = diagramsByType[type];
                return (
                  <TabsContent key={type} value={type} className="mt-4">
                    {diagram ? (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <div>
                            <h3 className="font-semibold capitalize">{diagram.diagram_type} Diagram</h3>
                            <p className="text-sm text-muted-foreground">
                              {diagram.file_count} files • {diagram.component_count} components
                              {diagram.ai_enhanced && " • AI Enhanced"}
                            </p>
                          </div>
                        </div>
                        <MermaidDiagram 
                          content={diagram.diagram_content}
                          className="mt-3"
                        />
                        <Button
                          variant="outline"
                          onClick={() => {
                            const element = document.createElement("a");
                            element.setAttribute(
                              "href",
                              "data:text/plain;charset=utf-8," +
                                encodeURIComponent(diagram.diagram_content)
                            );
                            element.setAttribute("download", `${type}-diagram.mmd`);
                            element.style.display = "none";
                            document.body.appendChild(element);
                            element.click();
                            document.body.removeChild(element);
                          }}
                        >
                          📥 Download Diagram
                        </Button>
                      </div>
                    ) : (
                      <p className="text-muted-foreground">No diagram generated</p>
                    )}
                  </TabsContent>
                );
              })}
            </Tabs>
          </CardContent>
        </Card>

        {/* Data Flows */}
        {flows.length > 0 && (
          <Card className="mb-8 border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle>Data Flow Paths</CardTitle>
              <CardDescription>How data flows through your application</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {flows.map((flow) => (
                <div key={flow.id} className="rounded-lg border border-slate-200 p-4">
                  <h3 className="font-semibold text-slate-900">{flow.flow_name}</h3>
                  <p className="text-sm text-slate-600 mt-2">
                    <span className="font-mono bg-slate-100 px-2 py-1 rounded">{flow.start_component}</span>
                    <span className="mx-2">→</span>
                    <span className="font-mono bg-slate-100 px-2 py-1 rounded">{flow.end_component}</span>
                  </p>
                  {flow.steps.length > 0 && (
                    <div className="mt-3">
                      <p className="text-sm font-medium text-slate-700 mb-2">Steps:</p>
                      <ol className="space-y-1 list-decimal list-inside">
                        {flow.steps.map((step, idx) => (
                          <li key={idx} className="text-sm text-slate-600">
                            {step}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                  {flow.description && (
                    <p className="text-sm text-slate-600 mt-3 italic">{flow.description}</p>
                  )}
                </div>
              ))}
            </CardContent>
          </Card>
        )}

        {/* Summary */}
        <Card className="border-slate-200 shadow-sm bg-gradient-to-br from-slate-50 to-slate-100">
          <CardHeader>
            <CardTitle>Analysis Summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Total Files Analyzed</p>
                <p className="text-2xl font-bold text-slate-900">
                  {diagrams[0]?.file_count || "N/A"}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Components</p>
                <p className="text-2xl font-bold text-slate-900">
                  {diagrams[0]?.component_count || "N/A"}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Data Flows</p>
                <p className="text-2xl font-bold text-slate-900">{flows.length}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
