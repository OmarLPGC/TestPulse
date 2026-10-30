import { BrowserRouter } from "react-router-dom";

import { Dashboard } from "./features/projects/ProjectPages";

export default function App() {
  return (
    <BrowserRouter>
      <Dashboard />
    </BrowserRouter>
  );
}
