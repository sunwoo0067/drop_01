"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Product } from "@/types";
import { Loader2 } from "lucide-react";

export default function ProductListPage() {
    const [products, setProducts] = useState<Product[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchProducts = async () => {
        try {
            // Assuming /api/sourcing/products endpoint exists or similar
            // If not, we might need to adjust. Based on previous crawls, /api/sourcing might have search endpoints.
            // Let's assume a generic GET /api/sourcing/products for now or check backend.
            // Using /products based on router prefix '/api/products' and proxy /api -> backend:8000/api
            const response = await api.get("/products");
            setProducts(response.data);
        } catch (error) {
            console.error("Failed to fetch products", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProducts();
    }, []);

    const handleRegister = async (productId: string) => {
        try {
            if (!confirm("Register this product to Coupang?")) return;
            await api.post(`/coupang/register/${productId}`); // Adjust endpoint as per backend implementation
            alert("Registration initiated!");
            fetchProducts(); // Refresh
        } catch (error) {
            console.error("Registration failed", error);
            alert("Registration failed");
        }
    };

    if (loading) {
        return (
            <div className="flex justify-center items-center h-64">
                <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            </div>
        );
    }

    return (
        <div>
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-3xl font-bold text-gray-800">Product List</h1>
                <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md font-medium transition-colors">
                    Refresh
                </button>
            </div>

            <div className="bg-white rounded-lg shadow overflow-hidden border border-gray-200">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Image</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Price</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {products.map((product) => (
                            <tr key={product.id} className="hover:bg-gray-50">
                                <td className="px-6 py-4 whitespace-nowrap">
                                    {product.processed_image_urls && product.processed_image_urls.length > 0 ? (
                                        <img src={product.processed_image_urls[0]} alt={product.name} className="h-12 w-12 object-cover rounded" />
                                    ) : (
                                        <div className="h-12 w-12 bg-gray-200 rounded animate-pulse" />
                                    )}
                                </td>
                                <td className="px-6 py-4">
                                    <div className="text-sm font-medium text-gray-900 line-clamp-2">{product.processed_name || product.name}</div>
                                    <div className="text-xs text-gray-500">{product.brand}</div>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                                    {product.selling_price.toLocaleString()} KRW
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap">
                                    <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${product.processing_status === 'COMPLETED' ? 'bg-green-100 text-green-800' :
                                        product.processing_status === 'FAILED' ? 'bg-red-100 text-red-800' :
                                            'bg-yellow-100 text-yellow-800'
                                        }`}>
                                        {product.processing_status}
                                    </span>
                                </td>
                                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                                    <button
                                        onClick={() => handleRegister(product.id)}
                                        className="text-indigo-600 hover:text-indigo-900 mr-4"
                                    >
                                        Register
                                    </button>
                                    <a href={`/products/${product.id}`} className="text-gray-600 hover:text-gray-900">
                                        Edit
                                    </a>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
