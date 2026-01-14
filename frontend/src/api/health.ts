import client from './client';
import type { HealthStatus, ExternalServiceStatus, BackgroundTask } from '@/lib/types';

export async function getHealthStatus(): Promise<HealthStatus> {
  const response = await client.get<HealthStatus>('/');
  return response.data;
}

export async function getDetailedHealth(): Promise<HealthStatus> {
  const response = await client.get<HealthStatus>('/detailed');
  return response.data;
}

export async function getExternalServicesHealth(): Promise<ExternalServiceStatus> {
  const response = await client.get<ExternalServiceStatus>('/external');
  return response.data;
}

export async function getTaskStatus(
  taskType?: string,
  limit: number = 20
): Promise<{ total: number; tasks: BackgroundTask[] }> {
  const response = await client.get('/tasks', {
    params: { task_type: taskType, limit },
  });
  return response.data;
}

export default {
  getHealthStatus,
  getDetailedHealth,
  getExternalServicesHealth,
  getTaskStatus,
};
