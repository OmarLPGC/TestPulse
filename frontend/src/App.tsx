import { BrowserRouter } from "react-router-dom";

import { AuthProvider } from "./auth/AuthContext";
import { AuthRoutes } from "./auth/AuthRoutes";
import { Dashboard } from "./features/projects/ProjectPages";
import { WorkspaceProvider } from "./features/workspaces/WorkspaceContext";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AuthRoutes>
          <WorkspaceProvider>
            <Dashboard />
          </WorkspaceProvider>
        </AuthRoutes>
      </BrowserRouter>
    </AuthProvider>
  );
}
