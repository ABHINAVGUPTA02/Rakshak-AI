import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import Chat from './pages/Chat';
import CrimeMap from './pages/CrimeMap';
import CrimeRecords from './pages/CrimeRecords';
import Dashboard from './pages/Dashboard';
import NetworkGraph from './pages/NetworkGraph';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/map" element={<CrimeMap />} />
          <Route path="/network" element={<NetworkGraph />} />
          <Route path="/records" element={<CrimeRecords />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
