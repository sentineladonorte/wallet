'use client'

import React from 'react';
import HighchartsReact from 'highcharts-react-official';
import Highcharts from 'highcharts/highstock';
import { useFormat } from '@/lib/privacy';
import { Order } from '@/types';

Highcharts.setOptions({
  lang: {
    months: ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'],
    shortMonths: ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'],
    weekdays: ['domingo', 'segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado'],
    rangeSelectorZoom: 'Período',
    decimalPoint: ',',
    thousandsSep: '.',
  },
});

const isoToTimestamp = (iso: string) => {
  const [year, month, day] = iso.split('-').map(Number);
  return Date.UTC(year, month - 1, day);
};

const orderPoints = (orders: Order[], orderType: 1 | -1) =>
  orders
    .filter((order) => order.order_type === orderType && order.kind === 'trade')
    .map((order) => [isoToTimestamp(order.date), order.price])
    .sort((a, b) => a[0] - b[0]);

const AXIS_STYLE = {
  gridLineColor: '#2a2a28',
  lineColor: '#383835',
  tickColor: '#383835',
  labels: { style: { color: '#98978d' } },
};

const Stock: React.FC<{ data: number[][]; orders: Order[] }> = ({ data, orders }) => {
  const { hidden } = useFormat();
  // O preço é de mercado, mas os pontos revelariam o preço pago em cada boleta.
  const visibleOrders = hidden ? [] : orders;
  const options: Highcharts.Options = {
    chart: { backgroundColor: 'transparent', style: { fontFamily: 'inherit' } },
    credits: { enabled: false },
    legend: { enabled: true, itemStyle: { color: '#c3c2b7' }, itemHoverStyle: { color: '#f0efec' } },
    navigator: { enabled: false },
    scrollbar: { enabled: false },
    rangeSelector: {
      selected: 3,
      buttons: [
        { type: 'month', count: 1, text: '1M' },
        { type: 'month', count: 3, text: '3M' },
        { type: 'month', count: 6, text: '6M' },
        { type: 'year', count: 1, text: '1A' },
        { type: 'all', text: 'Tudo' },
      ],
      inputEnabled: false,
      buttonTheme: {
        fill: 'transparent',
        style: { color: '#98978d' },
        states: {
          hover: { fill: '#242422', style: { color: '#f0efec' } },
          select: { fill: '#242422', style: { color: '#f0efec' } },
        },
      },
      labelStyle: { color: '#98978d' },
    },
    tooltip: { backgroundColor: '#242422', borderColor: '#383835', style: { color: '#f0efec' }, valuePrefix: 'R$ ', valueDecimals: 2 },
    xAxis: { ...AXIS_STYLE, type: 'datetime' },
    yAxis: { ...AXIS_STYLE, title: { text: 'R$', style: { color: '#98978d' } }, opposite: false },
    series: [
      { type: 'line', name: 'Preço', data, color: '#3987e5', lineWidth: 2 },
      {
        type: 'scatter', name: 'Compra', data: orderPoints(visibleOrders, 1), color: '#0ca30c',
        marker: { enabled: true, symbol: 'triangle', radius: 6 }, tooltip: { pointFormat: 'Compra: <b>R$ {point.y:.2f}</b>' },
      },
      {
        type: 'scatter', name: 'Venda', data: orderPoints(visibleOrders, -1), color: '#d03b3b',
        marker: { enabled: true, symbol: 'triangle-down', radius: 6 }, tooltip: { pointFormat: 'Venda: <b>R$ {point.y:.2f}</b>' },
      },
    ],
  };

  return <HighchartsReact highcharts={Highcharts} constructorType="stockChart" options={options} />;
};

export default Stock;
