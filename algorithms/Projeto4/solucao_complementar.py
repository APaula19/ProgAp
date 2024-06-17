from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterBoolean,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsSpatialIndex,
    QgsPointXY,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingException,
    QgsProcessingOutputVectorLayer,
    QgsProject,
)
from PyQt5.QtCore import QVariant
from qgis import processing
class ValidateAndCreatePointsAlgorithm1(QgsProcessingAlgorithm):

    INPUT_MASSA_DAGUA_LAYER = 'INPUT_MASSA_DAGUA_LAYER'
    INPUT_BARRAGEM_LAYER = 'INPUT_BARRAGEM_LAYER'
    OUTPUT_POINT_LAYER = 'OUTPUT_POINT_LAYER'
    CLASSIFY_FEATURES = 'CLASSIFY_FEATURES'

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_MASSA_DAGUA_LAYER,
                'Massa d\'água Layer',
                [QgsProcessing.TypeVectorPolygon]
            )
        )
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_BARRAGEM_LAYER,
                'Barragem Layer',
                [QgsProcessing.TypeVectorLine]
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.OUTPUT_POINT_LAYER,
                'Output Point Layer'
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.CLASSIFY_FEATURES,
                'Classify Features',
                defaultValue=True
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        #Obter os parâmetros
        massa_dagua_layer = self.parameterAsVectorLayer(parameters, self.INPUT_MASSA_DAGUA_LAYER, context)
        barragem_layer = self.parameterAsVectorLayer(parameters, self.INPUT_BARRAGEM_LAYER, context)
        output_point_layer = self.parameterAsSink(parameters, self.OUTPUT_POINT_LAYER, context, QgsFields(), QgsWkbTypes.Point, massa_dagua_layer.crs())
        classify_features = self.parameterAsBool(parameters, self.CLASSIFY_FEATURES, context)

        #Validar bordas de massa d'água
        invalid_features = self.validate_borda_intersections(massa_dagua_layer, barragem_layer, feedback)

        #Criar pontos conforme condições da barragem
        self.create_points_from_barragem(barragem_layer, output_point_layer, classify_features)

        #Retorna resultados
        return {self.OUTPUT_POINT_LAYER: output_point_layer}

    def validate_borda_intersections(self, massa_dagua_layer, barragem_layer, feedback):
        invalid_features = []

        barragem_index = QgsSpatialIndex(barragem_layer.getFeatures())

        massa_dagua_layer.startEditing()
        classificacao_idx = massa_dagua_layer.fields().indexOf("Classificacao")

        if classificacao_idx == -1:
            new_field = QgsField("Classificacao", QVariant.String)
            massa_dagua_layer.dataProvider().addAttributes([new_field])
            massa_dagua_layer.updateFields()
            classificacao_idx = massa_dagua_layer.fields().indexOf("Classificacao")

        total_count = massa_dagua_layer.featureCount()
        step = total_count / 100 if total_count > 100 else 1
        current_count = 0

        for massa_dagua_feature in massa_dagua_layer.getFeatures():
            if feedback.isCanceled():
                break

            massa_dagua_geom = massa_dagua_feature.geometry()
            vertices = massa_dagua_geom.vertices()

            invalid = False
            for vertex in vertices:
                if feedback.isCanceled():
                    break

                point = QgsGeometry.fromPointXY(QgsPointXY(vertex))
                ids = barragem_index.intersects(point.boundingBox())

                if ids:
                    for fid in ids:
                        barragem_feature = barragem_layer.getFeature(fid)
                        barragem_geom = barragem_feature.geometry()
                        if point.within(barragem_geom):
                            invalid = True
                            break
                if invalid:
                    break

            if invalid:
                invalid_features.append(massa_dagua_feature)
                massa_dagua_feature.setAttribute(classificacao_idx, "erro borda")
                print(f"Erro de borda encontrado: Feature ID {massa_dagua_feature.id()}")
            else:
                massa_dagua_feature.setAttribute(classificacao_idx, "Correto")

            massa_dagua_layer.updateFeature(massa_dagua_feature)

            #Atualizar progresso a cada feição processada
            current_count += 1
            feedback.setProgress(int(current_count / total_count * 100))

        massa_dagua_layer.commitChanges()

        if invalid_features:
            print(f"Foram encontradas {len(invalid_features)} bordas inválidas.")
        else:
            print("Não há bordas inválidas para atualizar.")

        return invalid_features

    def create_points_from_barragem(self, barragem_layer, output_point_layer, classify_features):
        #Obter IDs sobrepostos
        sobrepostos_ids = set()
        via_deslocamento_layer = QgsProject.instance().mapLayersByName('dados_projeto4_2024 — infra_via_deslocamento_l')[0]
        via_deslocamento_ids = set(feature.id() for feature in via_deslocamento_layer.getFeatures())

        for feature in barragem_layer.getFeatures():
            if feature.id() in via_deslocamento_ids:
                sobrepostos_ids.add(feature.id())

        #Criar pontos no output
        fields = QgsFields()
        fields.append(QgsField('id', QVariant.Int))
        fields.append(QgsField('Classificação', QVariant.String))

        for feature in barragem_layer.getFeatures():
            #Adicionar pontos conforme condições
            if feature.id() in sobrepostos_ids and feature['sobreposto_transportes'] != 1:
                self.add_point_feature(output_point_layer, feature, 'Erro 7')

            elif feature.id() not in sobrepostos_ids and feature['sobreposto_transportes'] == 1:
                self.add_point_feature(output_point_layer, feature, 'Erro 7')

    def add_point_feature(self, output_point_layer, feature, classificacao):
        new_feature = QgsFeature()
        geometry = feature.geometry()

        if geometry.isMultipart():
            multiline = geometry.asMultiPolyline()
            first_point = multiline[0][0]  # Primeiro ponto da primeira linha
        else:
            line = geometry.asPolyline()
            first_point = line[0]  # Primeiro ponto da linha

        new_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(first_point)))
        new_feature.setAttributes([feature.id(), classificacao])
        output_point_layer.addFeature(new_feature)

    def tr(self, string):
        return QgsProcessingAlgorithm.tr(string)

    def createInstance(self):
        return ValidateAndCreatePointsAlgorithm1()

    def name(self):
        return 'validate_and_create_points_algorithm'

    def displayName(self):
        return self.tr('Validate and Create Points Algorithm')

    def group(self):
        return self.tr('Projeto 4')

    def groupId(self):
        return 'projeto4'

    def shortHelpString(self):
        return self.tr("This algorithm validates borders and creates points based on specified conditions.")

#Registrar o algoritmo para que seja exibido na interface de processamento do QGIS
processing.registry().addAlgorithm(ValidateAndCreatePointsAlgorithm1())

'''Código sem o uso de processing separado por regras
Regra 6: Verificar se a borda da massa d'água está sobreposta a uma barragem

from qgis.core import (
    QgsProject, QgsFeature, QgsField, QgsGeometry, QgsSpatialIndex, QgsPointXY
)
from PyQt5.QtCore import QVariant

def validate_borda_intersections(massa_dagua_layer, barragem_layer):
    invalid_features = []

    barragem_index = QgsSpatialIndex(barragem_layer.getFeatures())

    massa_dagua_layer.startEditing()
    classificacao_idx = massa_dagua_layer.fields().indexOf("Classificacao")

    if classificacao_idx == -1:
        new_field = QgsField("Classificacao", QVariant.String)
        massa_dagua_layer.dataProvider().addAttributes([new_field])
        massa_dagua_layer.updateFields()
        classificacao_idx = massa_dagua_layer.fields().indexOf("Classificacao")

    for massa_dagua_feature in massa_dagua_layer.getFeatures():
        massa_dagua_geom = massa_dagua_feature.geometry()
        vertices = massa_dagua_geom.vertices()

        invalid = False
        for vertex in vertices:
            point = QgsGeometry.fromPointXY(QgsPointXY(vertex))
            ids = barragem_index.intersects(point.boundingBox())

            if ids:
                for fid in ids:
                    barragem_feature = barragem_layer.getFeature(fid)
                    barragem_geom = barragem_feature.geometry()
                    if point.within(barragem_geom):
                        invalid = True
                        break
            if invalid:
                break

        if invalid:
            invalid_features.append(massa_dagua_feature)
            massa_dagua_feature.setAttribute(classificacao_idx, "erro borda")
            print(f"Erro de borda encontrado: Feature ID {massa_dagua_feature.id()}")
        else:
            massa_dagua_feature.setAttribute(classificacao_idx, "Correto")

        massa_dagua_layer.updateFeature(massa_dagua_feature)

    massa_dagua_layer.commitChanges()

    if invalid_features:
        print(f"Foram encontradas {len(invalid_features)} bordas inválidas.")
    else:
        print("Não há bordas inválidas para atualizar.")

    return invalid_features

# Nomes das camadas
massa_dagua_layer_name = "dados_projeto4_2024 — cobter_massa_dagua_a"
barragem_layer_name = "dados_projeto4_2024 — infra_barragem_l"

# Obter as camadas do projeto
massa_dagua_layer = QgsProject.instance().mapLayersByName(massa_dagua_layer_name)
barragem_layer = QgsProject.instance().mapLayersByName(barragem_layer_name)

# Verificar se as camadas foram encontradas
if not massa_dagua_layer or not barragem_layer:
    print("Uma ou ambas as camadas não foram encontradas.")
else:
    massa_dagua_layer = massa_dagua_layer[0]
    barragem_layer = barragem_layer[0]

    # Realizar a validação das interseções de borda
    invalid_features = validate_borda_intersections(massa_dagua_layer, barragem_layer)

    # Verificar se houve feições inválidas e exibir mensagem adequada
    if invalid_features:
        print("Classificação das feições inválidas na camada de massa d'água atualizada para 'erro borda'.")
    else:
        print("Não há bordas inválidas para atualizar.")

Regra 7: Criar pontos conforme condições da barragem

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsPointXY,
    QgsFields
)
from qgis.PyQt.QtCore import QVariant

# Carregar camadas
barragem_layer = QgsProject.instance().mapLayersByName('dados_projeto4_2024 — infra_barragem_l')[0]
via_deslocamento_layer = QgsProject.instance().mapLayersByName('dados_projeto4_2024 — infra_via_deslocamento_l')[0]

# Obter IDs sobrepostos
sobrepostos_ids = set()
via_deslocamento_ids = set(feature.id() for feature in via_deslocamento_layer.getFeatures())

for feature in barragem_layer.getFeatures():
    if feature.id() in via_deslocamento_ids:
        sobrepostos_ids.add(feature.id())

# Criar nova camada de pontos
fields = QgsFields()
fields.append(QgsField('id', QVariant.Int))
fields.append(QgsField('Classificação', QVariant.String))

new_layer = QgsVectorLayer('Point?crs=EPSG:4326', 'erro_7_pontos', 'memory')
new_layer.dataProvider().addAttributes(fields)
new_layer.updateFields()

for feature in barragem_layer.getFeatures():
    # Adicionar pontos que satisfazem a condição 1 e não têm o atributo "sobreposto_transportes" preenchido com 1
    if feature.id() in sobrepostos_ids and feature['sobreposto_transportes'] != 1:
        new_feature = QgsFeature()
        
        # Obter o primeiro ponto da geometria, tratando MultiLineString
        geometry = feature.geometry()
        if geometry.isMultipart():
            multiline = geometry.asMultiPolyline()
            first_point = multiline[0][0]  # Primeiro ponto da primeira linha
        else:
            line = geometry.asPolyline()
            first_point = line[0]  # Primeiro ponto da linha
        
        new_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(first_point)))
        new_feature.setAttributes([feature.id(), 'Erro 7'])
        new_layer.dataProvider().addFeature(new_feature)
        
    # Adicionar pontos que não satisfazem a condição 1, mas têm o atributo "sobreposto_transportes" preenchido como 1
    elif feature.id() not in sobrepostos_ids and feature['sobreposto_transportes'] == 1:
        new_feature = QgsFeature()
        
        # Obter o primeiro ponto da geometria, tratando MultiLineString
        geometry = feature.geometry()
        if geometry.isMultipart():
            multiline = geometry.asMultiPolyline()
            first_point = multiline[0][0]  # Primeiro ponto da primeira linha
        else:
            line = geometry.asPolyline()
            first_point = line[0]  # Primeiro ponto da linha
        
        new_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(first_point)))
        new_feature.setAttributes([feature.id(), 'Erro 7'])
        new_layer.dataProvider().addFeature(new_feature)

# Adicionar a nova camada ao projeto
QgsProject.instance().addMapLayer(new_layer)


'''
