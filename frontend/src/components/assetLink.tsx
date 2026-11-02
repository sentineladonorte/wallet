import React from 'react';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import { investidor10Url } from '@/lib/assets';

/** Nome do ativo com link para a página dele no Investidor10, quando ela existe. */
const AssetLink: React.FC<{ name: string; assetClass: string | null | undefined; className?: string; label?: string }> = ({
  name, assetClass, className = '', label,
}) => {
  const url = investidor10Url(assetClass, name);
  if (!url) return label ? null : <span className={`font-medium ${className}`}>{name}</span>;

  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      title={`Abrir ${name} no Investidor10`}
      className={`inline-flex items-center gap-1 font-medium text-accent hover:underline ${className}`}
    >
      {label ?? name}
      <OpenInNewIcon sx={{ fontSize: 13 }} />
    </a>
  );
};

export default AssetLink;
