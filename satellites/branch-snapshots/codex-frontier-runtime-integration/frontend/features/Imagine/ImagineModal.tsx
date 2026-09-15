/**
 * Image Generation Modal v11.0.0 (Imagine Pipeline)
 * Generate images with OpenAI gpt-image-1, Gemini Nano Banana, and Grok Imagine
 */

import React, { useState, useCallback, useEffect } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Platform, Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
import { toast } from '../../components/Toast';
const API_URL = API_BASE;

interface ImagineModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  onImageGenerated?: (imageData: string) => void;
}

interface Provider {
  id: string;
  name: string;
  capabilities: string[];
  status: string;
}

export const ImagineModal: React.FC<ImagineModalProps> = ({
  visible, onClose, colors, onImageGenerated
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [negativePrompt, setNegativePrompt] = useState('');
  const [provider, setProvider] = useState('auto');
  const [style, setStyle] = useState<string | null>(null);
  const [size, setSize] = useState('1024x1024');
  const [quality, setQuality] = useState('standard');
  const [result, setResult] = useState<any>(null);
  const [providers, setProviders] = useState<Provider[]>([]);

  const styles_list = [
    'realistic', 'photorealistic', 'cartoon', 'anime', 'watercolor',
    'oil_painting', 'digital_art', '3d_render', 'pixel_art', 'sketch',
    'cyberpunk', 'fantasy', 'sci-fi', 'minimalist', 'abstract'
  ];

  const sizes = ['256x256', '512x512', '1024x1024', '1792x1024', '1024x1792'];

  useEffect(() => {
    if (visible) {
      loadProviders();
    }
  }, [visible]);

  const loadProviders = async () => {
    try {
      const response = await apiFetch(`${API_URL}/api/imagine/info`);
      const data = await response.json();
      setProviders(data.providers || []);
    } catch (error) {
      console.error('Failed to load providers:', error);
    }
  };

  const generateImage = useCallback(async () => {
    if (!prompt.trim()) {
      toast.error('Please describe the image you want to generate');
      return;
    }
    
    setIsLoading(true);
    setResult(null);
    
    try {
      const response = await apiFetch(`${API_URL}/api/imagine/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          provider,
          style,
          size,
          quality,
          negative_prompt: negativePrompt || null,
          count: 1,
        }),
      });
      
      const data = await response.json();
      setResult(data);
      
      if (data.status === 'success' && data.images?.[0]?.data && onImageGenerated) {
        onImageGenerated(data.images[0].data);
      }
    } catch (error: any) {
      toast.error(`Image generation failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt, provider, style, size, quality, negativePrompt]);

  const enhancePrompt = useCallback(async () => {
    if (!prompt.trim()) {
      toast.error('Please enter a prompt to enhance');
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await apiFetch(`${API_URL}/api/imagine/enhance-prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt,
          style,
          provider: 'grok',
        }),
      });
      
      const data = await response.json();
      if (data.enhanced_prompt) {
        setPrompt(data.enhanced_prompt);
        toast.info('Your prompt has been enhanced by AI');
      }
    } catch (error: any) {
      toast.error(`Enhancement failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [prompt, style]);

  return (
    <Modal visible={visible} animationType="slide" transparent={false}>
      <View style={[localStyles.container, { backgroundColor: colors.background }]}>
        <View style={[localStyles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={localStyles.closeBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={[localStyles.title, { color: colors.text }]}>🎨 Imagine Pipeline</Text>
          <View style={localStyles.placeholder} />
        </View>

        <ScrollView style={localStyles.content} showsVerticalScrollIndicator={false}>
          {/* Provider Selection */}
          <Text style={[localStyles.label, { color: colors.text }]}>🤖 AI Provider</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={localStyles.providerScroll}>
            <TouchableOpacity
              style={[
                localStyles.providerChip,
                { backgroundColor: provider === 'auto' ? colors.primary : colors.cardBackground, borderColor: colors.border }
              ]}
              onPress={() => setProvider('auto')}
            >
              <Text style={[localStyles.providerText, { color: provider === 'auto' ? '#FFF' : colors.text }]}>✨ Auto</Text>
            </TouchableOpacity>
            {providers.map((p) => (
              <TouchableOpacity
                key={p.id}
                style={[
                  localStyles.providerChip,
                  { backgroundColor: provider === p.id ? colors.primary : colors.cardBackground, borderColor: colors.border }
                ]}
                onPress={() => setProvider(p.id)}
              >
                <Text style={[localStyles.providerText, { color: provider === p.id ? '#FFF' : colors.text }]}>{p.name}</Text>
                <View style={[localStyles.statusDot, { backgroundColor: p.status === 'active' ? '#10B981' : '#EF4444' }]} />
              </TouchableOpacity>
            ))}
          </ScrollView>

          {/* Prompt Input */}
          <Text style={[localStyles.label, { color: colors.text, marginTop: 16 }]}>📝 Describe Your Image</Text>
          <TextInput
            style={[localStyles.textArea, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
            placeholder="A majestic dragon flying over a mountain at sunset, detailed scales, volumetric lighting..."
            placeholderTextColor={colors.textSecondary}
            value={prompt}
            onChangeText={setPrompt}
            multiline
            numberOfLines={4}
          />
          
          <TouchableOpacity
            style={[localStyles.enhanceBtn, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}
            onPress={enhancePrompt}
            disabled={isLoading}
          >
            <Ionicons name="sparkles" size={16} color={colors.primary} />
            <Text style={[localStyles.enhanceBtnText, { color: colors.primary }]}>Enhance with AI</Text>
          </TouchableOpacity>

          {/* Negative Prompt */}
          <Text style={[localStyles.label, { color: colors.text, marginTop: 16 }]}>🚫 Negative Prompt (Optional)</Text>
          <TextInput
            style={[localStyles.input, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
            placeholder="blurry, low quality, distorted..."
            placeholderTextColor={colors.textSecondary}
            value={negativePrompt}
            onChangeText={setNegativePrompt}
          />

          {/* Style Selection */}
          <Text style={[localStyles.label, { color: colors.text, marginTop: 16 }]}>🎨 Style</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <TouchableOpacity
              style={[
                localStyles.styleChip,
                { backgroundColor: !style ? colors.primary : colors.cardBackground, borderColor: colors.border }
              ]}
              onPress={() => setStyle(null)}
            >
              <Text style={[localStyles.styleText, { color: !style ? '#FFF' : colors.text }]}>None</Text>
            </TouchableOpacity>
            {styles_list.map((s) => (
              <TouchableOpacity
                key={s}
                style={[
                  localStyles.styleChip,
                  { backgroundColor: style === s ? colors.primary : colors.cardBackground, borderColor: colors.border }
                ]}
                onPress={() => setStyle(s)}
              >
                <Text style={[localStyles.styleText, { color: style === s ? '#FFF' : colors.text }]}>
                  {s.replace('_', ' ')}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {/* Size Selection */}
          <Text style={[localStyles.label, { color: colors.text, marginTop: 16 }]}>📏 Size</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            {sizes.map((s) => (
              <TouchableOpacity
                key={s}
                style={[
                  localStyles.sizeChip,
                  { backgroundColor: size === s ? colors.primary : colors.cardBackground, borderColor: colors.border }
                ]}
                onPress={() => setSize(s)}
              >
                <Text style={[localStyles.sizeText, { color: size === s ? '#FFF' : colors.text }]}>{s}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          {/* Quality Selection */}
          <Text style={[localStyles.label, { color: colors.text, marginTop: 16 }]}>✨ Quality</Text>
          <View style={localStyles.qualityRow}>
            <TouchableOpacity
              style={[
                localStyles.qualityChip,
                { backgroundColor: quality === 'standard' ? colors.primary : colors.cardBackground, borderColor: colors.border }
              ]}
              onPress={() => setQuality('standard')}
            >
              <Text style={[localStyles.qualityText, { color: quality === 'standard' ? '#FFF' : colors.text }]}>Standard</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[
                localStyles.qualityChip,
                { backgroundColor: quality === 'hd' ? colors.primary : colors.cardBackground, borderColor: colors.border }
              ]}
              onPress={() => setQuality('hd')}
            >
              <Text style={[localStyles.qualityText, { color: quality === 'hd' ? '#FFF' : colors.text }]}>HD</Text>
            </TouchableOpacity>
          </View>

          {/* Generate Button */}
          <TouchableOpacity
            style={[localStyles.generateBtn, { backgroundColor: colors.primary }]}
            onPress={generateImage}
            disabled={isLoading}
          >
            {isLoading ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <>
                <Ionicons name="image" size={20} color="#FFF" />
                <Text style={localStyles.generateBtnText}>Generate Image</Text>
              </>
            )}
          </TouchableOpacity>

          {/* Result */}
          {result && (
            <View style={[localStyles.resultCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
              <Text style={[localStyles.resultTitle, { color: colors.text }]}>
                {result.status === 'success' ? '✅ Image Generated' : '⚠️ Generation Result'}
              </Text>
              <Text style={[localStyles.resultProvider, { color: colors.textSecondary }]}>
                Provider: {result.provider} | Model: {result.model}
              </Text>
              
              {result.images?.[0]?.data && (
                <Image
                  source={{ uri: `data:image/png;base64,${result.images[0].data}` }}
                  style={localStyles.generatedImage}
                  resizeMode="contain"
                />
              )}
              
              {result.images?.[0]?.enhanced_prompt && (
                <View style={[localStyles.promptPreview, { backgroundColor: colors.codeBackground }]}>
                  <Text style={[localStyles.promptLabel, { color: colors.primary }]}>Enhanced Prompt:</Text>
                  <Text style={[localStyles.promptText, { color: colors.text }]}>
                    {result.images[0].enhanced_prompt.substring(0, 300)}...
                  </Text>
                </View>
              )}
              
              {result.error && (
                <Text style={[localStyles.errorText, { color: '#EF4444' }]}>{result.error}</Text>
              )}
            </View>
          )}
        </ScrollView>
      </View>
    </Modal>
  );
};

const localStyles = StyleSheet.create({
  container: { flex: 1, paddingTop: Platform.OS === 'ios' ? 50 : 30 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1 },
  closeBtn: { padding: 8 },
  title: { fontSize: 18, fontWeight: 'bold' },
  placeholder: { width: 40 },
  content: { flex: 1, padding: 16 },
  label: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
  providerScroll: { marginBottom: 8 },
  providerChip: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 20, marginRight: 8, borderWidth: 1, gap: 6 },
  providerText: { fontSize: 12, fontWeight: '500' },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  textArea: { borderWidth: 1, borderRadius: 8, padding: 12, fontSize: 14, minHeight: 100, textAlignVertical: 'top' },
  input: { borderWidth: 1, borderRadius: 8, padding: 12, fontSize: 14 },
  enhanceBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 10, borderRadius: 8, marginTop: 8, borderWidth: 1, gap: 6 },
  enhanceBtnText: { fontSize: 13, fontWeight: '500' },
  styleChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 16, marginRight: 8, borderWidth: 1 },
  styleText: { fontSize: 12, fontWeight: '500', textTransform: 'capitalize' },
  sizeChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 16, marginRight: 8, borderWidth: 1 },
  sizeText: { fontSize: 12, fontWeight: '500' },
  qualityRow: { flexDirection: 'row', gap: 12 },
  qualityChip: { flex: 1, paddingVertical: 12, borderRadius: 8, alignItems: 'center', borderWidth: 1 },
  qualityText: { fontSize: 14, fontWeight: '500' },
  generateBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 16, borderRadius: 10, marginTop: 24, gap: 8 },
  generateBtnText: { color: '#FFF', fontSize: 16, fontWeight: '600' },
  resultCard: { marginTop: 20, padding: 16, borderRadius: 12, borderWidth: 1 },
  resultTitle: { fontSize: 16, fontWeight: 'bold', marginBottom: 4 },
  resultProvider: { fontSize: 12, marginBottom: 12 },
  generatedImage: { width: '100%', height: 300, borderRadius: 8, marginBottom: 12 },
  promptPreview: { padding: 12, borderRadius: 8 },
  promptLabel: { fontSize: 12, fontWeight: '600', marginBottom: 4 },
  promptText: { fontSize: 12, lineHeight: 18 },
  errorText: { fontSize: 12, marginTop: 8 },
});

export default ImagineModal;
