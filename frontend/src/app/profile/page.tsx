'use client'

import React from 'react';
import PersonIcon from '@mui/icons-material/Person';
import { Card, ErrorState, LoadingState, PageHeader } from '@/components/ui';
import { useApi } from '@/lib/useApi';
import { User } from '@/types';

const Profile: React.FC = () => {
  const { data: user, isLoading, error, reload } = useApi<User>('/user');

  return (
    <>
      <PageHeader title="Perfil" />
      <Card className="max-w-md">
        {isLoading && !user && <LoadingState />}
        {error && !user && <ErrorState message={error} onRetry={reload} />}
        {user && (
          <div className="flex items-center gap-4">
            <span className="flex items-center justify-center w-12 h-12 rounded-full bg-raised text-soft">
              <PersonIcon />
            </span>
            <div className="min-w-0">
              <p className="font-semibold truncate">{user.name || user.username}</p>
              <p className="text-sm text-muted truncate">{user.email}</p>
            </div>
          </div>
        )}
      </Card>
    </>
  );
};

export default Profile;
