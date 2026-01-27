import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { MainDashboard } from './components/MainDashboard';
import { DevDashboard } from './components/DevDashboard';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainDashboard />} />
        <Route path="/dev" element={<DevDashboard />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;