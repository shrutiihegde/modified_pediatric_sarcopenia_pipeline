# Usage: python3 L3_finder.py --dicom_dir /workspace/Shruti_sarcopenia_segmentation/data/test/ST-test_MRI001 --model_path /Shruti_sarcopenia_segmentation/pediatric_sarcopenia_pipeline/models/models/l3/child_9_slice_w_transfer_fold_3.h5 --output_directory /workspace/Shruti_sarcopenia_segmentation/data/test/L3finder_output --save_plots

from matplotlib import pyplot as plt

from argparse import ArgumentParser
import itertools
import sys
import traceback

import attr
import pdb
import toolz

from l3finder.ingest import find_subjects, separate_series, \
    construct_series_for_subjects_without_sagittals
from l3finder.exclude import filter_axial_series, filter_sagittal_series, \
        load_series_to_skip_pickle_file, remove_series_to_skip
from l3finder.output import output_l3_images_to_h5, output_images
# from l3finder.predict import make_predictions_for_sagittal_mips
from l3finder.preprocess import create_sagittal_mip, preprocess_images, \
    group_mips_by_dimension, create_sagittal_mips_from_series
from util.reify import reify
from util.investigate import load_subject_ids_to_investigate

def pcs_debugger(type, value, tb):
    traceback.print_exception(type, value, tb)
    pdb.pm()

sys.excepthook = pcs_debugger

@attr.s
class SagittalMIP:
    source_preprocessed_image = attr.ib()

    @property
    def subject_id(self):
        return self.source_preprocessed_image.source_series.subject.id_

    @property
    def preprocessed_image(self):
        return self.source_preprocessed_image

    @property
    def series(self):
        return self.source_preprocessed_image.source_series
    # series = attr.ib()
    # preprocessed_image = attr.ib()

    # @property
    # def subject_id(self):
        # return self.series.subject.id_

def parse_args():
    parser = ArgumentParser()

    parser.add_argument(
        '--dicom_dir',
        required=True,
        help='Root directory containing dicoms in format output by Tim\'s '
             'script. That is subject_1/accession_xyz/series{sagittal & '
             'axial}. The accession directory should contain both a sagittal '
             'preprocessed_image series and an axial preprocessed_image series. '
    )
    parser.add_argument(
        '--new_tim_dicom_dir_structure',
        action='store_true',
        help='Gets subjects in the format used for the 10000 pt dataset versus that used for the 380 pt dataset'
    )
    parser.add_argument(
        '--model_path',
        required=True,
        help='Path to .h5 model trained using '
             'https://github.com/fk128/ct-slice-detection Unet model. '
    )

    parser.add_argument(
        '--output_directory',
        required=True,
        help='Path to directory where output files will be saved. Will be '
             'created if it does not exist '
    )

    parser.add_argument(
        '--show_plots',
        action='store_true',
        help='Path to directory where output files will be saved'
    )

    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite files within target folder'
    )

    parser.add_argument(
        '--save_plots',
        action='store_true',
        help='If true, will save side-by-side plot of predicted L3 and the '
             'axial slice at that level '
    )

    parser.add_argument(
        "--series_to_skip_pickle_file",
        help="Pickle file of series dumped from identify_broken_dicoms.py"
    )

    parser.add_argument(
        '--cache_intermediate_results',
        action='store_true',
        help='If true, will cache the results of some of the longer running '
             'computations in the passed --cache_dir. Note: there is no check to make'
             'sure that you actually passed a dir'
    )

    parser.add_argument(
        "--cache_dir",
        help="Directory to store cached files in. If none given, no caching"
    )

    return parser.parse_args()

def main():
    args = parse_args()

    l3_images = find_l3_images(config=vars(args))

    print("Outputting images")
    output_images(
        l3_images,
        args=dict(
            output_directory=args.output_directory,
            should_plot=args.show_plots,
            should_overwrite=args.overwrite,
            should_save_plots=args.save_plots
        )
    )
    return l3_images

def find_l3_images(config):
    print("Finding subjects")

    subjects = list(
        find_subjects(
            config["dicom_dir"],
            new_tim_dir_structure=config["new_tim_dicom_dir_structure"]
        )
    )
    
    print('Subjects found: ', len(subjects))
    
    print("Subjects:",subjects)
    
    print("Finding series")
    
#     for s in subjects:
#         print(s.find_series())
    
#     series = list((s.find_series() for s in subjects)) 
    series = list(flatten(s.find_series() for s in subjects))
    
    print("Series:",series)
    exclusions = []

    print("Separating series")
    sagittal_series, axial_series, excluded_series = separate_series(series)

    # print("SHORTENING for development")
    # sagittal_series = sagittal_series[:20]
    # axial_series = axial_series[:20]
    # investigate = set(["Z1243452", "Z1238033"])
    # investigate = set(load_subject_ids_to_investigate('/opt/smi/areas_differ_by_gt_10_pct.txt'))
    # sagittal_series = [s for s in sagittal_series if s.subject.id_ in investigate]
    # axial_series = [s for s in axial_series if s.subject.id_ in investigate]

    print("Filtering out unwanted series")
    axial_series, ax_exclusions = filter_axial_series(axial_series)
    exclusions.extend(ax_exclusions)

    constructed_sagittals = construct_series_for_subjects_without_sagittals(
        subjects, sagittal_series, axial_series
    )

    print(
        "Series separated\n",
        len(sagittal_series), "sagittal series.",
        len(axial_series), "axial series.",
        len(excluded_series), "excluded series.",
        len(constructed_sagittals), "constructed series.",
    )

    if config.get("series_to_skip_pickle_file", False):
        print("Removing unwanted series")
        series_to_skip = load_series_to_skip_pickle_file(
            config["series_to_skip_pickle_file"])
        sagittal_series = remove_series_to_skip(series_to_skip, sagittal_series)
        axial_series = remove_series_to_skip(series_to_skip, axial_series)

    # print("Just using constructed sagittals for now...")
    # sagittal_series = constructed_sagittals
    sagittal_series.extend(constructed_sagittals)
    sagittal_series, sag_exclusions = filter_sagittal_series(sagittal_series)
    exclusions.extend(sag_exclusions)

    print("Creating sagittal MIPS")
    mips = create_sagittal_mips_from_series(
        many_series=sagittal_series,
        cache_dir=config.get("cache_dir", None),
        cache=config.get("cache_intermediate_results", False),
    )
    # spacings = [series.spacing for series in sagittal_series]

    print("Preprocessing Images")
    preprocessed_images = preprocess_images(mips)

    # Sagittal mip is redundant, get rid just use preprocessed images
    sagittal_mips = [SagittalMIP(i) for i in preprocessed_images]

    print("Separate heights for better batching")
    mips_by_dimension = group_mips_by_dimension(sagittal_mips)
    print("Dimensions in set:", mips_by_dimension.keys())

    print("Making predictions")
    prediction_results = []
    for dimension, sagittal_mips in mips_by_dimension.items():
        dim_group_results = make_predictions_for_sagittal_mips(
            sagittal_mips,
            model_path=config["model_path"],
            shape=dimension,
        )
        prediction_results.extend(dim_group_results)
    l3_images = build_l3_images(axial_series, prediction_results)
    return l3_images, exclusions

def flatten(sequence):
    """Converts array of arrays into just an array of items"""
    print("Sequence",*sequence)
    return itertools.chain(*sequence)

def build_l3_images(axial_series, prediction_results):
    """
    Pairs axial series with L3 location predictions based on
    subject ID.
    """
    axials_with_prediction_results = toolz.join(
        leftkey=lambda ax: ax.subject.id_,
        leftseq=axial_series,
        rightkey=lambda pred_res: pred_res[0].input_mip.subject_id,
        rightseq=prediction_results
    )
    #print(prediction_results[0][0].input_mip)
    """
    file1 = open('/workspace/Shruti_sarcopenia_segmentation/pediatric_sarcopenia_pipeline/outputs/out.txt', 'w')
    file1.writelines(str(prediction_results[0]))
    file1.close()
    """
    
    l3_images = [
        L3Image(
            sagittal_series=result[0].input_mip.series,
            axial_series=ax,
            prediction_result=result
            )
        for ax, result in axials_with_prediction_results
    ]
    return l3_images

@attr.s
class L3Image:
    axial_series = attr.ib()
    sagittal_series = attr.ib()
    prediction_result = attr.ib()

    @property
    def pixel_data(self):
        return self.axial_series.image_at_pos_in_px(
            self.prediction_result.prediction.predicted_y_in_px,
            sagittal_z_pos_pair=self.sagittal_series.z_range_pair
        )
    
    def pixel_data_manualL3(self, manualL3):
        # Provide manual L3 location starting with 1 (not 0).
        return self.axial_series.image_at_manualL3(manualL3)

    @property
    def height_of_sagittal_image(self):
        return self.sagittal_series.resolution[0]

    @property
    def number_of_axial_dicoms(self):
        return self.axial_series.number_of_dicoms

    @property
    def subject_id(self):
        return self.axial_series.subject.id_

    @reify
    def prediction_index(self):
        index, metadata = self.axial_series.image_index_at_pos(
            self.prediction_result.prediction.predicted_y_in_px,
            sagittal_z_pos_pair=self.sagittal_series.z_range_pair
        )
        return index, metadata

    def as_csv_row(self):
        prediction = self.prediction_result.prediction
        prediction_index, l3_axial_slice_metadata = self.prediction_index
        row = [
            self.axial_series.id_,
            prediction.predicted_y_in_px,
            prediction.probability,
            self.sagittal_series.series_path,
            self.axial_series.series_path,
        ]
        row.extend(l3_axial_slice_metadata.as_csv_row())
        return row

    @property
    def predicted_y_in_px(self):
        return self.prediction_result.prediction.predicted_y_in_px

    def free_pixel_data(self):
        """Frees the memory used in the underlying ImageSeries objects"""
        self.axial_series.free_pixel_data()
        self.sagittal_series.free_pixel_data()

if __name__ == "__main__":
    l3_images = main()






