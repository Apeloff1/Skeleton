/**
 * API Helper with Retry Logic and Connection Stability v11.0.0
 * 
 * Provides robust API calls with:
 * - Automatic retry with exponential backoff
 * - Request deduplication
 * - Offline detection
 * - Error normalization
 */

import { Platform } from 'react-native';
import NetInfo from '@react-native-community/netinfo';

import { API_BASE } from './apiBase';

const API_URL = API_BASE;

interface ApiConfig {
  maxRetries: number;
  baseDelay: number;
  maxDelay: number;
  timeout: number;
}

const DEFAULT_CONFIG: ApiConfig = {
  maxRetries: 3,
  baseDelay: 1000,
  maxDelay: 10000,
  timeout: 30000,
};

interface ApiResponse<T = any> {
  data: T | null;
  error: string | null;
  status: number;
  success: boolean;
  retries: number;
}

// Request deduplication cache
const pendingRequests = new Map<string, Promise<ApiResponse>>();

// Connection state
let isOffline = false;

// Initialize network listener
if (Platform.OS !== 'web') {
  NetInfo.addEventListener(state => {
    isOffline = !state.isConnected;
  });
}

/**
 * Sleep with exponential backoff
 */
const sleep = (attempt: number, config: ApiConfig): Promise<void> => {
  const delay = Math.min(config.baseDelay * Math.pow(2, attempt), config.maxDelay);
  const jitter = delay * 0.2 * Math.random();
  return new Promise(resolve => setTimeout(resolve, delay + jitter));
};

/**
 * Generate request key for deduplication
 */
const getRequestKey = (endpoint: string, method: string, body?: any): string => {
  const bodyHash = body ? JSON.stringify(body).slice(0, 100) : '';
  return `${method}:${endpoint}:${bodyHash}`;
};

/**
 * Make API request with retry logic
 */
async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {},
  config: Partial<ApiConfig> = {}
): Promise<ApiResponse<T>> {
  const fullConfig = { ...DEFAULT_CONFIG, ...config };
  const url = `${API_URL}${endpoint}`;
  const requestKey = getRequestKey(endpoint, options.method || 'GET', options.body);
  
  // Check for pending duplicate request
  const pending = pendingRequests.get(requestKey);
  if (pending && options.method === 'GET') {
    return pending;
  }
  
  const executeRequest = async (): Promise<ApiResponse<T>> => {
    let lastError: string = '';
    let retries = 0;
    
    for (let attempt = 0; attempt <= fullConfig.maxRetries; attempt++) {
      // Check offline status
      if (isOffline) {
        return {
          data: null,
          error: 'No internet connection. Please check your network.',
          status: 0,
          success: false,
          retries: attempt,
        };
      }
      
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), fullConfig.timeout);
        
        const response = await fetch(url, {
          ...options,
          headers: {
            'Content-Type': 'application/json',
            ...options.headers,
          },
          signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
        
        if (response.ok) {
          const data = await response.json();
          return {
            data,
            error: null,
            status: response.status,
            success: true,
            retries: attempt,
          };
        }
        
        // Handle specific error codes
        if (response.status === 401) {
          return {
            data: null,
            error: 'Authentication required. Please log in again.',
            status: response.status,
            success: false,
            retries: attempt,
          };
        }
        
        if (response.status === 403) {
          return {
            data: null,
            error: 'Access denied. You don\'t have permission for this action.',
            status: response.status,
            success: false,
            retries: attempt,
          };
        }
        
        if (response.status === 404) {
          return {
            data: null,
            error: 'Resource not found.',
            status: response.status,
            success: false,
            retries: attempt,
          };
        }
        
        if (response.status === 429) {
          // Rate limited - wait longer
          await sleep(attempt + 2, fullConfig);
          lastError = 'Too many requests. Please wait a moment.';
          retries = attempt;
          continue;
        }
        
        if (response.status >= 500) {
          // Server error - retry
          lastError = `Server error (${response.status}). Retrying...`;
          retries = attempt;
          if (attempt < fullConfig.maxRetries) {
            await sleep(attempt, fullConfig);
            continue;
          }
        }
        
        // Try to get error message from response
        try {
          const errorData = await response.json();
          lastError = errorData.detail || errorData.message || errorData.error || `Error ${response.status}`;
        } catch {
          lastError = `Request failed with status ${response.status}`;
        }
        
      } catch (error: any) {
        if (error.name === 'AbortError') {
          lastError = 'Request timed out. Please try again.';
        } else if (error.message?.includes('Network')) {
          lastError = 'Network error. Please check your connection.';
        } else {
          lastError = error.message || 'Unknown error occurred';
        }
        
        retries = attempt;
        
        if (attempt < fullConfig.maxRetries) {
          await sleep(attempt, fullConfig);
          continue;
        }
      }
    }
    
    return {
      data: null,
      error: lastError || 'Request failed after multiple attempts',
      status: 0,
      success: false,
      retries,
    };
  };
  
  const promise = executeRequest();
  
  // Cache GET requests for deduplication
  if (options.method === 'GET' || !options.method) {
    pendingRequests.set(requestKey, promise);
    promise.finally(() => {
      pendingRequests.delete(requestKey);
    });
  }
  
  return promise;
}

/**
 * API client with typed methods
 */
export const api = {
  /**
   * GET request
   */
  get: <T = any>(endpoint: string, config?: Partial<ApiConfig>): Promise<ApiResponse<T>> => {
    return apiRequest<T>(endpoint, { method: 'GET' }, config);
  },
  
  /**
   * POST request
   */
  post: <T = any>(endpoint: string, body: any, config?: Partial<ApiConfig>): Promise<ApiResponse<T>> => {
    return apiRequest<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(body),
    }, config);
  },
  
  /**
   * PUT request
   */
  put: <T = any>(endpoint: string, body: any, config?: Partial<ApiConfig>): Promise<ApiResponse<T>> => {
    return apiRequest<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body),
    }, config);
  },
  
  /**
   * DELETE request
   */
  delete: <T = any>(endpoint: string, config?: Partial<ApiConfig>): Promise<ApiResponse<T>> => {
    return apiRequest<T>(endpoint, { method: 'DELETE' }, config);
  },
  
  /**
   * PATCH request
   */
  patch: <T = any>(endpoint: string, body: any, config?: Partial<ApiConfig>): Promise<ApiResponse<T>> => {
    return apiRequest<T>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }, config);
  },
  
  /**
   * Health check
   */
  healthCheck: async (): Promise<boolean> => {
    try {
      const response = await apiRequest('/api/health', { method: 'GET' }, { maxRetries: 1, timeout: 5000 });
      return response.success;
    } catch {
      return false;
    }
  },
  
  /**
   * Get offline status
   */
  isOffline: (): boolean => isOffline,
};

export default api;
