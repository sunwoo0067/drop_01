export default function Home() {
  return (
    <div>
      <h1 className="text-3xl font-bold mb-6 text-gray-800">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-lg shadow-md border border-gray-100">
          <h2 className="text-xl font-semibold mb-2 text-gray-700">Total Products</h2>
          <p className="text-3xl font-bold text-blue-600">Loading...</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-md border border-gray-100">
          <h2 className="text-xl font-semibold mb-2 text-gray-700">Pending Processing</h2>
          <p className="text-3xl font-bold text-orange-500">Loading...</p>
        </div>
        <div className="bg-white p-6 rounded-lg shadow-md border border-gray-100">
          <h2 className="text-xl font-semibold mb-2 text-gray-700">Listed on Coupang</h2>
          <p className="text-3xl font-bold text-green-600">Loading...</p>
        </div>
      </div>
    </div>
  );
}
