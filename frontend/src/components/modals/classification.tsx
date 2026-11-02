'use client'

import React, { FormEvent, useState } from 'react';
import { Button, Field, Modal, inputClass } from '@/components/ui';
import { useToast } from '@/components/ui/toast';
import { errorMessage } from '@/lib/useApi';
import api from '@/services/api';
import { Position } from '@/types';

const unique = (values: (string | null)[]) =>
  Array.from(new Set(values.filter((value): value is string => Boolean(value)))).sort();

const ClassificationModal: React.FC<{
  asset: Position;
  assets: Position[];
  onClose: () => void;
  onSaved: () => void;
}> = ({ asset, assets, onClose, onSaved }) => {
  const toast = useToast();
  const [category, setCategory] = useState(asset.category ?? '');
  const [subCategory, setSubCategory] = useState(asset.sub_category ?? '');
  const [isSaving, setIsSaving] = useState(false);
  const sameClass = assets.filter((item) => item.asset_class === asset.asset_class);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    try {
      await api.patch(`/asset/${encodeURIComponent(asset.name)}/classification`, { category, sub_category: subCategory });
      toast(`Classificação de ${asset.name} atualizada`);
      onSaved();
      onClose();
    } catch (error) {
      toast(errorMessage(error, 'Não foi possível salvar a classificação'), 'error');
      setIsSaving(false);
    }
  };

  return (
    <Modal title={`Classificar ${asset.name}`} onClose={onClose}>
      <form onSubmit={save} className="space-y-4">
        <p className="text-sm text-muted">Define como o ativo aparece nas visões de categoria e subcategoria.</p>
        <Field label="Categoria" htmlFor="category">
          <input id="category" list="categories" maxLength={32} className={inputClass} value={category} onChange={(event) => setCategory(event.target.value)} />
          <datalist id="categories">
            {unique(sameClass.map((item) => item.category)).map((value) => <option key={value} value={value} />)}
          </datalist>
        </Field>
        <Field label="Subcategoria" htmlFor="subCategory">
          <input id="subCategory" list="subCategories" maxLength={32} className={inputClass} value={subCategory} onChange={(event) => setSubCategory(event.target.value)} />
          <datalist id="subCategories">
            {unique(sameClass.map((item) => item.sub_category)).map((value) => <option key={value} value={value} />)}
          </datalist>
        </Field>
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="primary" disabled={isSaving}>Salvar</Button>
        </div>
      </form>
    </Modal>
  );
};

export default ClassificationModal;
