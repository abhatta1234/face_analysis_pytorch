import numpy as np
import argparse
from os import makedirs, path
from model.race_head import RaceHead
from model.gender_head import GenderHead
from model.age_head import AgeHead
from model.resnet import ResNet
from utils.model_loader import load_state
from data.data_loader_predict import PredictionDataLoader
import torch
from tqdm import tqdm
from torch.nn import DataParallel


class Predictor():
    def __init__(self, race_model_path, gender_model_path, age_model_path, source, image_list, dest,
                 net_mode, depth, batch_size, workers, drop_ratio, device):

        self.loader = PredictionDataLoader(batch_size, workers, source, image_list)
        self.predictions = np.asarray(self.loader.dataset.samples)
        self.race_model, self.race_head = None, None
        self.gender_model, self.gender_head = None, None
        self.age_model, self.age_head = None, None
        self.device = device
        self.save_file = path.join(dest, path.split(image_list)[1][:-4] + '_predictions.txt')

        if race_model_path:
            self.race_model, self.race_head = self.create_model(depth, drop_ratio, net_mode,
                                                                race_model_path, RaceHead)
            self.race_model.eval()
            self.race_head.eval()

        if gender_model_path:
            self.gender_model, self.gender_head = self.create_model(depth, drop_ratio, net_mode,
                                                                    gender_model_path, GenderHead)
            self.gender_model.eval()
            self.gender_head.eval()

        if age_model_path:
            self.age_model, self.age_head = self.create_model(depth, drop_ratio, net_mode,
                                                              age_model_path, AgeHead)
            self.age_model.eval()
            self.age_head.eval()

    def create_model(self, depth, drop_ratio, net_mode, model_path, head):
        model = DataParallel(ResNet(depth, drop_ratio, net_mode)).to(self.device)
        head = DataParallel(head()).to(self.device)

        load_state(model, head, None, model_path, True)

        model.eval()
        head.eval()

        return model, head

    def get_predictions(self, imgs, model, head, all_outputs):
        embeddings = model(imgs)
        outputs = head(embeddings)

        all_outputs = torch.cat((all_outputs, outputs), 0)

        return all_outputs

    def predict(self):
        if self.race_model:
            race_outputs = torch.tensor([], device=device)

        if self.gender_model:
            gender_outputs = torch.tensor([], device=self.device)

        if self.age_model:
            age_outputs = torch.tensor([], device=self.device)

        with torch.no_grad():
            for imgs in tqdm(iter(self.loader)):
                imgs = imgs.to(device)

                if self.race_model:
                    race_outputs = self.get_predictions(imgs, self.race_model, self.race_head, race_outputs)

                if self.gender_model:
                    gender_outputs = self.get_predictions(imgs, self.gender_model,
                                                          self.gender_head, gender_outputs)

                if self.age_model:
                    age_outputs = self.get_predictions(imgs, self.age_model, self.age_head, age_outputs)

        if self.race_model:
            _, race_outputs = torch.max(race_outputs, 1)
            race_outputs = race_outputs.cpu().numpy()

        if self.gender_model:
            _, gender_outputs = torch.max(gender_outputs, 1)
            gender_outputs = gender_outputs.cpu().numpy()

        if self.age_model:
            age_outputs = age_outputs.cpu().numpy()
            age_outputs = np.round(age_outputs, 0)
            age_outputs = np.sum(age_outputs, axis=1)

        return race_outputs, gender_outputs, age_outputs

    def run(self):
        race_preds, gender_preds, age_preds = self.predict()

        if race_preds is not None:
            self.predictions = np.column_stack((self.predictions, race_preds))

        if gender_preds is not None:
            self.predictions = np.column_stack((self.predictions, gender_preds))

        if age_preds is not None:
            self.predictions = np.column_stack((self.predictions, age_preds))

        np.savetxt(self.save_file, self.predictions, delimiter=' ', fmt='%s')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Extract features with CNN')
    parser.add_argument('--source', '-s', help='Path to the images.')
    parser.add_argument('--image_list', '-i', help='File with images names.')
    parser.add_argument('--dest', '-d', help='Path to save the predictions.')
    parser.add_argument('--batch_size', '-b', help='Batch size.', default=96, type=int)
    parser.add_argument('--model', help='Path to model.',)
    parser.add_argument('--race_model', '-rm', help='Path to the race model.')
    parser.add_argument('--gender_model', '-gm', help='Path to the gender model.')
    parser.add_argument('--age_model', '-am', help='Path to the age model.')
    parser.add_argument('--net_mode', '-n', help='Residual type [ir, ir_se].', default='ir_se', type=str)
    parser.add_argument('--depth', '-dp', help='Number of layers [50, 100, 152].', default=50, type=int)
    parser.add_argument('--workers', '-w', help='Workers number.', default=4, type=int)

    args = parser.parse_args()

    if not path.exists(args.dest):
        makedirs(args.dest)

    drop_ratio = 0.4
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

    predictor = Predictor(args.race_model, args.gender_model, args.age_model, args.source, args.image_list,
                          args.dest, args.net_mode, args.depth, args.batch_size,
                          args.workers, drop_ratio, device)
    predictor.run()
