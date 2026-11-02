'use client'

import React from 'react';
import AssetTable from '@/components/assetTable';
import { Card, ErrorState, LoadingState, PageHeader } from '@/components/ui';
import { useApi } from '@/lib/useApi';
import { AssetInfo } from '@/types';

const AssetsPage: React.FC = () => {
  const { data, isLoading, error, reload } = useApi<AssetInfo[]>('/assets');

  return (
    <>
      <PageHeader title="Ativos" subtitle="Todos os ativos cadastrados, não só os da sua carteira." />
      <Card>
        {isLoading && !data && <LoadingState />}
        {error && !data && <ErrorState message={error} onRetry={reload} />}
        {data && <AssetTable assets={data} />}
      </Card>
    </>
  );
};

export default AssetsPage;
