import { type RouteConfig, index, route } from "@react-router/dev/routes";

export default [
	index("routes/home.tsx"),
	route("maintenance-requests", "routes/maintenance-requests.tsx"),
	route("architecture/:projectId", "routes/architecture.tsx"),
] satisfies RouteConfig;
